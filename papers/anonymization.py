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

# spaCy modelini yükle (önceden "en_core_web_sm" modelinin yüklü olduğundan emin olun)
nlp = spacy.load("en_core_web_sm")

# E-posta tespiti için regex
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

def process_page_text(page, process_limit, page_index, options, all_regions, skip_top=None):
    full_text = page.get_text("text")
    doc = nlp(full_text)

    lines = full_text.splitlines()
    top_text = "\n".join(lines[:max(1, int(0.2 * len(lines)))])

    # --- İSİM (PERSON) ---
    if options.get("anonymize_name", False):
        found_person = False
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                found_person = True
                rects = page.search_for(ent.text)
                for r in rects:
                    # Eğer hem skip_top hem process_limit varsa: r.y0 aralığının içinde olmalı
                    if skip_top is not None and process_limit is not None:
                        if not (r.y0 >= skip_top and r.y0 < process_limit):
                            continue
                    elif skip_top is not None:
                        if r.y0 < skip_top:
                            continue
                    elif process_limit is not None:
                        if r.y0 >= process_limit:
                            continue

                    all_regions.append({
                        "category": "name",
                        "text": ent.text,
                        "rect": [r.x0, r.y0, r.x1, r.y1],
                        "page": page_index
                    })
                    page.draw_rect(r, fill=(1, 1, 1))
                    page.insert_textbox(r, "********", fontsize=12, fontname="helv", color=(0, 0, 0), align=1)
        if not found_person:
            # Fallback: İlk %20 satırlarda, satırın tamamı büyük harf ya da isim formatına uygunsa
            for line in top_text.splitlines():
                candidate = line.strip()
                if candidate and len(candidate) < 150 and re.match(r'^([A-Z][a-zA-Z\*]+(?:,\s*[A-Z][a-zA-Z\*]+)+)$', candidate):
                    rects = page.search_for(candidate)
                    for r in rects:
                        if skip_top is not None and process_limit is not None:
                            if not (r.y0 >= skip_top and r.y0 < process_limit):
                                continue
                        elif skip_top is not None:
                            if r.y0 < skip_top:
                                continue
                        elif process_limit is not None:
                            if r.y0 >= process_limit:
                                continue

                        all_regions.append({
                            "category": "name",
                            "text": candidate,
                            "rect": [r.x0, r.y0, r.x1, r.y1],
                            "page": page_index
                        })
                        page.draw_rect(r, fill=(1, 1, 1))
                        page.insert_textbox(r, "********", fontsize=12, fontname="helv", color=(0, 0, 0), align=1)
                    break

    # --- E-POSTA (CONTACT) ---
    if options.get("anonymize_contact", False):
        for match in re.finditer(EMAIL_REGEX, full_text):
            email = match.group(0)
            rects = page.search_for(email)
            for r in rects:
                if skip_top is not None and process_limit is not None:
                    if not (r.y0 >= skip_top and r.y0 < process_limit):
                        continue
                elif skip_top is not None:
                    if r.y0 < skip_top:
                        continue
                elif process_limit is not None:
                    if r.y0 >= process_limit:
                        continue

                all_regions.append({
                    "category": "contact",
                    "text": email,
                    "rect": [r.x0, r.y0, r.x1, r.y1],
                    "page": page_index
                })
                page.draw_rect(r, fill=(1, 1, 1))
                page.insert_textbox(r, "********", fontsize=12, fontname="helv", color=(0, 0, 0), align=1)

    # --- KURUM (ORG) ---
    if options.get("anonymize_institution", False):
        found_org = False
        for ent in doc.ents:
            if ent.label_ == "ORG":
                if ent.text.lower() in ["eeg", "cnn", "convolutional neural network"]:
                    continue  # İstenmeyen org'ları atla
                found_org = True
                rects = page.search_for(ent.text)
                for r in rects:
                    if skip_top is not None and process_limit is not None:
                        if not (r.y0 >= skip_top and r.y0 < process_limit):
                            continue
                    elif skip_top is not None:
                        if r.y0 < skip_top:
                            continue
                    elif process_limit is not None:
                        if r.y0 >= process_limit:
                            continue

                    all_regions.append({
                        "category": "institution",
                        "text": ent.text,
                        "rect": [r.x0, r.y0, r.x1, r.y1],
                        "page": page_index
                    })
                    page.draw_rect(r, fill=(1, 1, 1))
                    page.insert_textbox(r, "********", fontsize=12, fontname="helv", color=(0, 0, 0), align=1)
        if not found_org:
            # Fallback: "University" veya "Institute" kelimesi geçen satırlar
            for line in top_text.splitlines():
                candidate = line.strip()
                if candidate and ("university" in candidate.lower() or "institute" in candidate.lower()):
                    rects = page.search_for(candidate)
                    for r in rects:
                        if skip_top is not None and process_limit is not None:
                            if not (r.y0 >= skip_top and r.y0 < process_limit):
                                continue
                        elif skip_top is not None:
                            if r.y0 < skip_top:
                                continue
                        elif process_limit is not None:
                            if r.y0 >= process_limit:
                                continue

                        all_regions.append({
                            "category": "institution",
                            "text": candidate,
                            "rect": [r.x0, r.y0, r.x1, r.y1],
                            "page": page_index
                        })
                        page.draw_rect(r, fill=(1, 1, 1))
                        page.insert_textbox(r, "********", fontsize=12, fontname="helv", color=(0, 0, 0), align=1)
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

    # 3) Giriş, İlgili Çalışmalar, Teşekkür sayfalarını atlama
    skip_section_keywords = ["giriş", "ilgili çalışmalar", "teşekkür"]
    skip_pages = set()
    for i in range(len(doc)):
        page = doc[i]
        txt_lower = page.get_text("text").lower()
        page_height = page.rect.height
        for keyword in skip_section_keywords:
            rects_keyword = page.search_for(keyword)
            if rects_keyword:
                for r in rects_keyword:
                    if r.y0 < 0.2 * page_height:
                        skip_pages.add(i)
                        break
            if i in skip_pages:
                break

    # 4) Tüm sayfaları dolaş
    for page_index in range(len(doc)):
        page = doc[page_index]

        # Skip sayfaları atla
        if page_index in skip_pages:
            continue

        # İlk sayfa için başlık bölgesini atlamak adına skip_top değeri belirle
        skip_top = None
        if page_index == 0:
            # Burada sayfa yüksekliğinin %15’i kadarını başlık bölgesi olarak kabul ediyoruz
            skip_top = 0.15 * page.rect.height

        # Abstract'a kadar (veya references sonrası) metin anonimleştirme
        process = False
        process_limit = None

        if abstract_page_index is not None:
            if page_index < abstract_page_index:
                process = True
            elif page_index == abstract_page_index:
                process = True
                process_limit = abstract_y  # Abstract kelimesinin üst sınırı
            elif references_page_index is not None and page_index > references_page_index:
                process = True
        else:
            # Abstract bulunamadıysa tüm sayfalar işlenebilir
            process = True

        # Metin anonimleştirme
        if process:
            process_page_text(page, process_limit, page_index, options, all_regions, skip_top=skip_top)

        # REFERENCES sonrası görsel bulanıklaştırma
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

def restore_original_fields(input_pdf_path, original_pdf_path, regions,
                            categories_to_restore, output_pdf_path):
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
            pix = orig_page.get_pixmap(clip=rect)
            img_bytes = pix.tobytes("png")

            # Arka planı beyaza boyayıp orijinal resmi veya metni geri koyuyoruz
            doc_page.draw_rect(rect, fill=(1,1,1))
            doc_page.insert_image(rect, stream=img_bytes)

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
    try:
        decrypted_json = decrypt_data(anonymized_data)
        regions = json.loads(decrypted_json)
        return restore_original_fields(
            input_pdf_path=input_pdf_path,
            original_pdf_path=input_pdf_path,
            regions=regions,
            categories_to_restore=["name", "contact", "institution", "image"],
            output_pdf_path=output_pdf_path
        )
    except Exception as e:
        print("merge_and_restore error:", e)
        return False
