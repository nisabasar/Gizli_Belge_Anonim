import re
import fitz  # PyMuPDF
import spacy
from PIL import Image, ImageFilter
import io
import json
import shutil

nlp = spacy.load("en_core_web_sm")
EMAIL_REGEX = r'[\w\.-]+@[\w\.-]+\.\w+'
SKIP_SECTIONS = ["introduction", "related works", "references", "acknowledgments"]

def is_skip_section(line):
    line_lower = line.strip().lower()
    return any(line_lower.startswith(section) for section in SKIP_SECTIONS)

def get_blurred_image_from_rect(page, rect, blur_radius=5):
    pix = page.get_pixmap(clip=rect)
    mode = "RGB" if pix.alpha == 0 else "RGBA"
    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    blurred = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    buf = io.BytesIO()
    blurred.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()

def anonymize_pdf(input_pdf_path, output_pdf_path, options=None):
    """
    PDF'in ilk sayfasındaki hassas alanları bulanıklaştırır ve
    tespit edilen alanların (kategori, orijinal metin, koordinatlar) listesini döndürür.
    """
    if options is None:
        options = {
            'anonymize_name': True,
            'anonymize_contact': True,
            'anonymize_institution': True
        }
    regions = []
    doc = fitz.open(input_pdf_path)
    page = doc[0]
    text = page.get_text("text")
    spacy_doc = nlp(text)
    TOP_THRESHOLD = 300

    # PERSON ve ORG varlıklarını tespit et
    for ent in spacy_doc.ents:
        if ent.label_ == "PERSON" and options.get('anonymize_name'):
            rects = page.search_for(ent.text)
            for rect in rects:
                if rect.y0 < TOP_THRESHOLD:
                    regions.append({
                        "category": "name",
                        "text": ent.text,
                        "rect": [rect.x0, rect.y0, rect.x1, rect.y1]
                    })
                    img_stream = get_blurred_image_from_rect(page, rect, blur_radius=5)
                    page.insert_image(rect, stream=img_stream)
        elif ent.label_ == "ORG" and options.get('anonymize_institution'):
            rects = page.search_for(ent.text)
            for rect in rects:
                if rect.y0 < TOP_THRESHOLD:
                    regions.append({
                        "category": "institution",
                        "text": ent.text,
                        "rect": [rect.x0, rect.y0, rect.x1, rect.y1]
                    })
                    img_stream = get_blurred_image_from_rect(page, rect, blur_radius=5)
                    page.insert_image(rect, stream=img_stream)
    # E-posta adreslerini tespit et (kategori "contact")
    for match in re.finditer(EMAIL_REGEX, text):
        email = match.group(0)
        rects = page.search_for(email)
        for rect in rects:
            if rect.y0 < TOP_THRESHOLD:
                regions.append({
                    "category": "contact",
                    "text": email,
                    "rect": [rect.x0, rect.y0, rect.x1, rect.y1]
                })
                img_stream = get_blurred_image_from_rect(page, rect, blur_radius=5)
                page.insert_image(rect, stream=img_stream)
    doc.save(output_pdf_path)
    doc.close()
    return regions

def restore_original_fields(anon_pdf_path, original_pdf_path, categories_to_restore, regions):
    import fitz
    import shutil
    try:
        # 1) PDF'i aç
        doc = fitz.open(anon_pdf_path)
        page = doc[0]
        # 2) Seçili alanların blur'unu kaldır
        for region in regions:
            if region["category"] in categories_to_restore:
                rect = fitz.Rect(region["rect"])
                page.draw_rect(rect, color=(1,1,1), fill=(1,1,1))
                page.insert_text(rect.tl, region["text"], fontsize=10, fontname="helv")
        # 3) Geçici dosyaya kaydet
        temp_path = anon_pdf_path + "_temp.pdf"
        doc.save(temp_path, incremental=False)
        doc.close()
        # 4) temp dosyasını orijinal dosyanın üzerine taşı
        shutil.move(temp_path, anon_pdf_path)
        return True
    except Exception as e:
        print("Restore işlemi hatası:", e)
        return False




def merge_review_comments(anon_pdf_path, review_text, final_path):
    try:
        doc = fitz.open(anon_pdf_path)
        first_page = doc[0]
        rect = first_page.rect
        new_page = doc.new_page(width=rect.width, height=rect.height)
        new_page.insert_text(
            fitz.Point(72, 72),
            "=== Hakem Yorumu ===\n" + review_text,
            fontsize=12,
            fontname="helv"
        )
        doc.save(final_path)
        doc.close()
        return True
    except Exception as e:
        print("Final PDF oluşturma hatası:", e)
        return False
