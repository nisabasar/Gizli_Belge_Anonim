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

nlp = spacy.load("en_core_web_sm")

EMAIL_REGEX = r'[\w\.-]+@[\w\.-]+\.\w+'

def encrypt_data(data_str):
    secret = "my_very_secret_key_for_encryption"
    key = hashlib.sha256(secret.encode('utf-8')).digest()
    data_bytes = data_str.encode('utf-8')
    padded_data = pad(data_bytes, AES.block_size)
    cipher = AES.new(key, AES.MODE_CBC)
    ciphertext = cipher.encrypt(padded_data)
    combined = cipher.iv + ciphertext
    return base64.b64encode(combined).decode('utf-8')

def decrypt_data(encrypted_str):
    secret = "my_very_secret_key_for_encryption"
    key = hashlib.sha256(secret.encode('utf-8')).digest()
    enc = base64.b64decode(encrypted_str)
    iv = enc[:AES.block_size]
    ciphertext = enc[AES.block_size:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded = cipher.decrypt(ciphertext)
    return unpad(padded, AES.block_size).decode('utf-8')

def blur_image_region(page, bbox, blur_radius=5):
    pix = page.get_pixmap(clip=bbox)
    mode = "RGB" if pix.alpha == 0 else "RGBA"
    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    blurred = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    buf = io.BytesIO()
    blurred.save(buf, format="PNG")
    buf.seek(0)
    page.draw_rect(bbox, fill=(1,1,1))
    page.insert_image(bbox, stream=buf.getvalue())


# --- Basit bir substitution cipher tablosu (örnek) ---
# Burada sadece a-z/A-Z harfleri dönüştürüyoruz. Diğer karakterleri olduğu gibi bırakıyoruz.
lower_map = {}
upper_map = {}
# Örnek olarak: 'a' -> '1', 'b' -> '2', ..., 'z' -> '26'
alphabet = "abcdefghijklmnopqrstuvwxyz"
for i, ch in enumerate(alphabet):
    lower_map[ch] = str(i+1)  # 'a'->'1', 'b'->'2', ...
    upper_map[ch.upper()] = str(i+1) + "*"  # 'A'->'1*', 'B'->'2*' vs.

def custom_cipher(original_text):
    """Her harfi substitution tablosuna göre dönüştüren basit bir fonksiyon."""
    result = []
    for ch in original_text:
        if ch in lower_map:
            result.append(lower_map[ch])
        elif ch in upper_map:
            result.append(upper_map[ch])
        else:
            # Harita dışında kalan karakterleri aynen koru (boşluk, rakam, noktalama vb.)
            result.append(ch)
    return "".join(result)


def process_page_text(page, process_limit, page_index, options, all_regions, skip_top=None):
    full_text = page.get_text("text")
    doc = nlp(full_text)

    # Manuel eklenmiş isim listesi (isterseniz)
    names_to_check = [
        "SUDHAKAR MISHRA",
        "Diksha Kalra",
        "S. Indu",
        "MOHAMMAD ASIF",
        "AJITHIA TEJAS VINODBHAI",
        "MAJITHIA TEJAS VINODBHAI",
        "UMA SHANKER TIWARY"
    ]

    # 1) İsim (PERSON)
    if options.get("anonymize_name", False):
        # a) spaCy PERSON
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                rects = page.search_for(ent.text)
                for r in rects:
                    if skip_top is not None and r.y0 < skip_top:
                        continue
                    if process_limit is not None and r.y0 >= process_limit:
                        continue

                    cipher_text = custom_cipher(ent.text)
                    all_regions.append({
                        "category": "name",
                        "text": ent.text,        # orijinal
                        "cipher": cipher_text,   # şifreli
                        "rect": [r.x0, r.y0, r.x1, r.y1],
                        "page": page_index
                    })

                    page.add_redact_annot(
                        r,
                        text=cipher_text,
                        fill=(1,1,1),
                    )

        # b) Manuel isim listesi
        for name in names_to_check:
            rects = page.search_for(name)
            for r in rects:
                if skip_top is not None and r.y0 < skip_top:
                    continue
                if process_limit is not None and r.y0 >= process_limit:
                    continue

                cipher_text = custom_cipher(name)
                all_regions.append({
                    "category": "name",
                    "text": name,
                    "cipher": cipher_text,
                    "rect": [r.x0, r.y0, r.x1, r.y1],
                    "page": page_index
                })

                page.add_redact_annot(
                    r,
                    text=cipher_text,
                    fill=(1,1,1),
                )

    # 2) E-POSTA
    if options.get("anonymize_contact", False):
        for match in re.finditer(EMAIL_REGEX, full_text):
            email = match.group(0)
            rects = page.search_for(email)
            for r in rects:
                if skip_top is not None and r.y0 < skip_top:
                    continue
                if process_limit is not None and r.y0 >= process_limit:
                    continue

                cipher_text = custom_cipher(email)
                all_regions.append({
                    "category": "contact",
                    "text": email,
                    "cipher": cipher_text,
                    "rect": [r.x0, r.y0, r.x1, r.y1],
                    "page": page_index
                })

                page.add_redact_annot(
                    r,
                    text=cipher_text,
                    fill=(1,1,1),
                )

    # 3) Kurum (ORG)
    if options.get("anonymize_institution", False):
        ignore_orgs = {"eeg", "cnn", "convolutional neural network", "ieee", "dataset", "svm"}
        for ent in doc.ents:
            if ent.label_ == "ORG" and ent.text.lower() not in ignore_orgs:
                rects = page.search_for(ent.text)
                for r in rects:
                    if skip_top is not None and r.y0 < skip_top:
                        continue
                    if process_limit is not None and r.y0 >= process_limit:
                        continue

                    cipher_text = custom_cipher(ent.text)
                    all_regions.append({
                        "category": "institution",
                        "text": ent.text,
                        "cipher": cipher_text,
                        "rect": [r.x0, r.y0, r.x1, r.y1],
                        "page": page_index
                    })

                    page.add_redact_annot(
                        r,
                        text=cipher_text,
                        fill=(1,1,1),
                    )

        # Fallback "University"/"Institute"
        lines = full_text.splitlines()
        for line in lines:
            candidate = line.strip()
            if candidate and ("university" in candidate.lower() or "institute" in candidate.lower()):
                rects = page.search_for(candidate)
                for r in rects:
                    if skip_top is not None and r.y0 < skip_top:
                        continue
                    if process_limit is not None and r.y0 >= process_limit:
                        continue

                    cipher_text = custom_cipher(candidate)
                    all_regions.append({
                        "category": "institution",
                        "text": candidate,
                        "cipher": cipher_text,
                        "rect": [r.x0, r.y0, r.x1, r.y1],
                        "page": page_index
                    })

                    page.add_redact_annot(
                        r,
                        text=cipher_text,
                        fill=(1,1,1),
                    )
                break

def anonymize_pdf(input_pdf_path, output_pdf_path, options=None):
    if options is None:
        options = {
            "anonymize_name": True,
            "anonymize_contact": True,
            "anonymize_institution": True,
            "blur_images": True
        }
    print("DEBUG: anonymize_pdf fonksiyonuna gelen options =", options)

    doc = fitz.open(input_pdf_path)
    all_regions = []

    # 1) Abstract/Özet sayfası bulma
    abstract_page_index = None
    abstract_y = None
    for i in range(len(doc)):
        page = doc[i]
        txt = page.get_text("text")
        m = re.search(r'\b(abstract|özet)\b', txt, re.IGNORECASE)
        if m:
            abstract_page_index = i
            rects = page.search_for(m.group(0))
            if rects:
                abstract_y = min(r.y0 for r in rects)
            break

    # 2) REFERENCES sayfası bulma
    references_page_index = None
    for i in range(len(doc)):
        page = doc[i]
        txt = page.get_text("text")
        if re.search(r'\bREFERENCES\b', txt):
            references_page_index = i
            break

    # 3) "giriş", "ilgili çalışmalar", "teşekkür" sayfalarını atla
    skip_section_keywords = ["giriş", "ilgili çalışmalar", "teşekkür"]
    skip_pages = set()
    for i in range(len(doc)):
        page = doc[i]
        page_height = page.rect.height
        txt_lower = page.get_text("text").lower()
        for kw in skip_section_keywords:
            kw_rects = page.search_for(kw)
            for r in kw_rects:
                if r.y0 < 0.2 * page_height:
                    skip_pages.add(i)
                    break
            if i in skip_pages:
                break

    # 4) Tüm sayfaları dolaş
    for page_index in range(len(doc)):
        page = doc[page_index]

        if page_index in skip_pages:
            continue

        skip_top = None
        if page_index == 0:
            skip_top = 0.15 * page.rect.height

        process = False
        process_limit = None

        if abstract_page_index is not None:
            if page_index < abstract_page_index:
                process = True
            elif page_index == abstract_page_index:
                process = True
                process_limit = abstract_y
            elif references_page_index is not None and page_index > references_page_index:
                process = True
        else:
            process = True

        if process:
            process_page_text(page, process_limit, page_index, options, all_regions, skip_top=skip_top)
            # Redaction anotasyonlarını uygula
            page.apply_redactions()

        # REFERENCES'tan sonra görsel bulanıklaştırma
        if references_page_index is not None and page_index > references_page_index and options.get("blur_images", True):
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

def custom_decipher(cipher_text):
    """
    custom_cipher ile şifrelenen metni tersine çevirir.
    Dikkat: Bu basit dönüşüm, bazı durumlarda (örneğin 10 vs. 1+0) belirsizlik yaratabilir.
    """
    lower_rev = {v: k for k, v in lower_map.items()}   # Örn: "1" -> "a", "2" -> "b", ..., "26" -> "z"
    upper_rev = {v: k for k, v in upper_map.items()}   # Örn: "1*" -> "A", "2*" -> "B", ..., "26*" -> "Z"
    
    result = []
    i = 0
    while i < len(cipher_text):
        if cipher_text[i].isdigit():
            j = i
            while j < len(cipher_text) and cipher_text[j].isdigit():
                j += 1
            # Eğer rakamları takip eden '*' varsa, uppercase harf
            if j < len(cipher_text) and cipher_text[j] == '*':
                num_str = cipher_text[i:j] + '*'
                if num_str in upper_rev:
                    result.append(upper_rev[num_str])
                else:
                    result.append(num_str)
                i = j + 1
            else:
                # Küçük harf için: önce iki haneli dene, yoksa tek haneli
                if i + 1 < len(cipher_text) and cipher_text[i:i+2] in lower_rev:
                    result.append(lower_rev[cipher_text[i:i+2]])
                    i += 2
                elif cipher_text[i] in lower_rev:
                    result.append(lower_rev[cipher_text[i]])
                    i += 1
                else:
                    # Eşleşme yoksa karakteri aynen ekle
                    result.append(cipher_text[i])
                    i += 1
        else:
            result.append(cipher_text[i])
            i += 1
    return "".join(result)

def restore_original_fields(input_pdf_path, original_pdf_path, regions,
                            categories_to_restore, output_pdf_path):
    import fitz
    doc = fitz.open(input_pdf_path)
    orig_doc = fitz.open(original_pdf_path)
    os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)

    for region in regions:
        cat = region.get("category", "")
        if cat not in categories_to_restore:
            continue
        page_num = region.get("page", 0)
        if page_num >= len(doc):
            continue

        coords = region.get("rect", [])
        if len(coords) != 4:
            continue

        rect = fitz.Rect(*coords)
        page = doc[page_num]

        if cat in ["name", "contact", "institution"]:
            cipher_text = region.get("cipher", "")
            if not cipher_text.strip():
                continue
            decrypted_text = custom_decipher(cipher_text)

            # Metni gerçekten PDF'ten sil:
            page.add_redact_annot(rect, text="", fill=None)
            page.apply_redactions()

            # Debug: dikdörtgen boyutunu ve metni yazdır
            print(f"Rect: {rect}, Decrypted: '{decrypted_text}'")

            # Metni ekle - basit bir (x, y) ile deneyin:
            x, y = rect.x0, rect.y0 + 2  # +2 piksel kaydırma
            page.insert_text(
                (x, y),
                decrypted_text,
                fontsize=8,
                color=(0, 0, 0),
                overlay=True
            )

        elif cat == "image":
            if page_num < len(orig_doc):
                orig_page = orig_doc[page_num]
                pix = orig_page.get_pixmap(clip=rect)
                img_bytes = pix.tobytes("png")
                page.insert_image(rect, stream=img_bytes, overlay=True)

    temp_path = output_pdf_path + ".temp"
    doc.save(temp_path)
    doc.close()
    orig_doc.close()
    os.replace(temp_path, output_pdf_path)
    return True

def merge_review_comments(input_pdf_path, review_text, output_pdf_path):
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

def merge_and_restore(input_pdf_path, anonymized_data, output_pdf_path, original_pdf_path):
    try:
        decrypted_json = decrypt_data(anonymized_data)
        regions = json.loads(decrypted_json)
        return restore_original_fields(
            input_pdf_path=input_pdf_path,
            original_pdf_path=original_pdf_path,  # <-- Gerçek orijinal PDF
            regions=regions,
            categories_to_restore=["name", "contact", "institution", "image"],
            output_pdf_path=output_pdf_path
        )
    except Exception as e:
        print("merge_and_restore error:", e)
        return False


