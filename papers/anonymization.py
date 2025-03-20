# papers/anonymization.py
import os
import re
import io
import json
import base64
import hashlib

import fitz  # PyMuPDF
import spacy
from PIL import Image, ImageFilter

from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import pad, unpad

# spaCy modelini yükle (öncesinde en_core_web_sm modelini yüklemiş olmalısınız)
nlp = spacy.load("en_core_web_sm")

# E-posta tespiti için regex
EMAIL_REGEX = r'[\w\.-]+@[\w\.-]+\.\w+'

# Metin aramada tüm sayfa için büyük bir threshold
TOP_THRESHOLD = 999999

SKIP_SECTIONS = ["introduction", "related works", "acknowledgments"]

def is_skip_section(line):
    line_lower = line.strip().lower()
    return any(line_lower.startswith(section) for section in SKIP_SECTIONS)

def encrypt_data(data_str):
    """
    Verilen stringi AES-256 CBC modunda şifreler ve Base64 kodlanmış string döndürür.
    """
    secret = "my_very_secret_key_for_encryption"  # Bu değeri gerçek projede güvenli bir şekilde yönetin!
    key = hashlib.sha256(secret.encode('utf-8')).digest()  # 32 baytlık AES-256 anahtarı
    data_bytes = data_str.encode('utf-8')
    padded_data = pad(data_bytes, AES.block_size)
    cipher = AES.new(key, AES.MODE_CBC)
    ciphertext = cipher.encrypt(padded_data)
    combined = cipher.iv + ciphertext  # IV + ciphertext
    return base64.b64encode(combined).decode('utf-8')

def decrypt_data(encrypted_str):
    """
    encrypt_data ile şifrelenmiş veriyi çözer.
    """
    secret = "my_very_secret_key_for_encryption"
    key = hashlib.sha256(secret.encode('utf-8')).digest()
    enc = base64.b64decode(encrypted_str)
    iv = enc[:AES.block_size]
    ciphertext = enc[AES.block_size:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded = cipher.decrypt(ciphertext)
    return unpad(padded, AES.block_size).decode('utf-8')

def blur_image_region(page, bbox, blur_radius=5):
    """
    Belirtilen 'bbox' (fitz.Rect) alanındaki resmi bulanıklaştırır:
      - Önce, ilgili alanı beyaz ile doldurur,
      - Ardından bulanıklaştırılmış resmi ekler.
    """
    pix = page.get_pixmap(clip=bbox)
    mode = "RGB" if pix.alpha == 0 else "RGBA"
    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    blurred = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    buf = io.BytesIO()
    blurred.save(buf, format="PNG")
    buf.seek(0)
    page.draw_rect(bbox, fill=(1, 1, 1))
    page.insert_image(bbox, stream=buf.getvalue())


def anonymize_pdf(input_pdf_path, output_pdf_path, options=None):
    """
    PDF üzerinde aşağıdaki işlemleri yapar:
      A) Tüm sayfalarda "mailto:" linklerini kaldırır.
      B) PDF’in başından "abstract" ya da "özet" kelimesi görünene kadar olan sayfalarda (yazar bilgileri bölgesi)
         spaCy kullanarak PERSON, ORG ve e-posta adreslerini tespit eder ve ilgili dikdörtgenleri beyazla doldurup,
         "********" ile değiştirir.
      C) PDF’de, herhangi bir sayfada **tamamen büyük harflerle** "REFERENCES" veya "KAYNAKÇA" kelimesi bulunursa,
         o sayfadan sonraki tüm sayfalardaki resim bloklarını bulanıklaştırır.
    Dönen değer, yapılan değişikliklerin kaydını içeren 'all_regions' listesidir.
    """
    if options is None:
        options = {
            'anonymize_name': True,
            'anonymize_contact': True,
            'anonymize_institution': True,
            'blur_images': True
        }
    doc = fitz.open(input_pdf_path)
    all_regions = []

    # --- 1. Metin anonimleştirme için sayfa belirleme:
    # Yazar bilgileri genellikle, PDF'in başından "abstract" veya "özet" kelimesi çıkana kadar yer alır.
    text_anonymize_pages = []
    for i in range(len(doc)):
        page = doc[i]
        txt = page.get_text("text").lower()
        if "abstract" in txt or "özet" in txt:
            break
        text_anonymize_pages.append(i)

    # --- 2. Resim bulanıklaştırması için başlangıç sayfası:
    # Herhangi bir sayfada, metin içinde "REFERENCES" veya "KAYNAKÇA" (tam büyük harflerle) varsa,
    # o sayfadan sonraki tüm sayfalarda resim blokları bulanıklaştırılacak.
    image_blur_start = None
    for i in range(len(doc)):
        page = doc[i]
        text = page.get_text("text")
        # "REFERENCES" ya da "KAYNAKÇA" kelimelerinin tam olarak büyük harflerle geçip geçmediğini kontrol et:
        if re.search(r'\bREFERENCES\b', text) or re.search(r'\bKAYNAKÇA\b', text):
            image_blur_start = i + 1
            break

    # --- 3. Tüm sayfaları dolaşarak işlemleri yap:
    for page_index in range(len(doc)):
        page = doc[page_index]
        # A) "mailto:" linklerini kaldır.
        for link in page.get_links():
            uri = link.get("uri", "")
            if uri.lower().startswith("mailto:"):
                page.delete_link(link)

        # B) Metin anonimleştirmesi: Sadece text_anonymize_pages içindeki sayfalarda.
        if page_index in text_anonymize_pages:
            text = page.get_text("text")
            spacy_doc = nlp(text)
            # Anonymize PERSON (yazar adı)
            if options.get('anonymize_name'):
                for ent in spacy_doc.ents:
                    if ent.label_ == "PERSON":
                        rects = page.search_for(ent.text)
                        for r in rects:
                            all_regions.append({
                                "category": "name",
                                "text": ent.text,
                                "rect": [r.x0, r.y0, r.x1, r.y1],
                                "page": page_index
                            })
                            page.draw_rect(r, fill=(1, 1, 1))
                            page.insert_textbox(r, "********", fontsize=12, fontname="helv", color=(0, 0, 0), align=1)
            # Anonymize ORG (kurum)
            if options.get('anonymize_institution'):
                for ent in spacy_doc.ents:
                    if ent.label_ == "ORG":
                        rects = page.search_for(ent.text)
                        for r in rects:
                            all_regions.append({
                                "category": "institution",
                                "text": ent.text,
                                "rect": [r.x0, r.y0, r.x1, r.y1],
                                "page": page_index
                            })
                            page.draw_rect(r, fill=(1, 1, 1))
                            page.insert_textbox(r, "********", fontsize=12, fontname="helv", color=(0, 0, 0), align=1)
            # Anonymize e-posta adresleri
            if options.get('anonymize_contact'):
                for match in re.finditer(EMAIL_REGEX, text):
                    email = match.group(0)
                    rects = page.search_for(email)
                    for r in rects:
                        all_regions.append({
                            "category": "contact",
                            "text": email,
                            "rect": [r.x0, r.y0, r.x1, r.y1],
                            "page": page_index
                        })
                        page.draw_rect(r, fill=(1, 1, 1))
                        page.insert_textbox(r, "********", fontsize=12, fontname="helv", color=(0, 0, 0), align=1)

        # C) Resim bulanıklaştırması: Yalnızca, eğer image_blur_start ayarlandıysa ve page_index >= image_blur_start ise.
        if image_blur_start is not None and page_index >= image_blur_start and options.get('blur_images'):
            rawdict = page.get_text("rawdict")
            for block in rawdict.get("blocks", []):
                if block.get("type") == 1 and "bbox" in block:
                    bbox = block["bbox"]
                    r = fitz.Rect(bbox)
                    all_regions.append({
                        "category": "image",
                        "rect": [r.x0, r.y0, r.x1, r.y1],
                        "page": page_index
                    })
                    blur_image_region(page, r, blur_radius=5)

    doc.save(output_pdf_path)
    doc.close()
    return all_regions


def restore_original_fields(input_pdf_path, original_pdf_path, regions,
                            categories_to_restore, output_pdf_path):
    """
    'regions' listesinde kaydedilen anonimleştirme alanlarını orijinal PDF'den geri yükler.
    Örneğin '["name","contact","institution","image"]' gibi kategoriler seçilebilir.
    """
    try:
        doc = fitz.open(input_pdf_path)
        orig_doc = fitz.open(original_pdf_path)

        os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)

        for region in regions:
            cat = region.get("category", "")
            if cat not in categories_to_restore:
                continue

            page_num = region.get("page", 0)
            if page_num >= len(doc) or page_num >= len(orig_doc):
                continue

            coords = region.get("rect", [])
            if len(coords) != 4:
                continue

            rect = fitz.Rect(*coords)

            doc_page = doc[page_num]
            orig_page = orig_doc[page_num]

            # Orijinal sayfadaki o dikdörtgeni al
            pix = orig_page.get_pixmap(clip=rect)
            img_bytes = pix.tobytes("png")

            # doc_page'deki alanı beyaza kapla, orijinal resmi bas
            doc_page.draw_rect(rect, fill=(1,1,1))
            doc_page.insert_image(rect, stream=img_bytes)

        # Kaydet
        temp_path = output_pdf_path + ".temp"
        doc.save(temp_path)
        doc.close()
        orig_doc.close()

        os.replace(temp_path, output_pdf_path)
        return True

    except Exception as e:
        print("restore_original_fields error:", e)
        return False


def merge_review_comments(input_pdf_path, review_text, output_pdf_path):
    """
    Anonimleştirilmiş PDF'ye (input_pdf_path) yeni bir sayfa ekleyip hakem değerlendirmesini ekler.
    """
    try:
        doc = fitz.open(input_pdf_path)
        os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
        page = doc.new_page(-1)
        page.insert_text((72, 72), review_text, fontsize=12)
        doc.save(output_pdf_path)
        doc.close()
        return True
    except Exception as e:
        print("merge_review_comments error:", e)
        return False


def merge_and_restore(input_pdf_path, anonymized_data, output_pdf_path):
    """
    Şifrelenmiş 'anonymized_data' stringi decrypt edip, JSON parse edip,
    restore_original_fields ile orijinal verileri geri yükler.
    """
    try:
        decrypted_json = decrypt_data(anonymized_data)  # Şifreli ise
        regions = json.loads(decrypted_json)
        # categories_to_restore örnek:
        return restore_original_fields(
            input_pdf_path=input_pdf_path,
            original_pdf_path=input_pdf_path,  # ya da orijinal PDF path'i
            regions=regions,
            categories_to_restore=["name","contact","institution","image"],
            output_pdf_path=output_pdf_path
        )
    except Exception as e:
        print("merge_and_restore error:", e)
        return False
