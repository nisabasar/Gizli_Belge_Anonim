import os
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

def restore_original_fields(input_pdf_path, original_pdf_path, regions, output_pdf_path):
    """
    input_pdf_path: Restore edilecek PDF (örneğin, reviewer tarafından oluşturulan, değerlendirme eklenmiş PDF)
    original_pdf_path: Yüklenen orijinal PDF'nin yolu
    regions: Anonymize sırasında kaydedilmiş blur yapılan alanların bilgileri.
             Örnek: [{"category": "contact", "text": "mzlyq@cust.edu.cn", "rect": [330.28, 164.92, 401.57, 174.89], "page": 0}, ...]
    output_pdf_path: Restore edilmiş PDF'nin kaydedileceği yeni dosya yolu.
    
    İşlev: input_pdf üzerindeki, blur yapılan alanları original_pdf'den alınan görüntüyle tamamen kapatıp,
           restore edilmiş PDF'yi output_pdf_path'e kaydeder.
    """
    try:
        doc = fitz.open(input_pdf_path)
        orig_doc = fitz.open(original_pdf_path)
        # Çıktı klasörünü oluştur (eğer yoksa)
        os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
        
        for region in regions:
            # Eğer "rect" anahtarı varsa, ondan al
            if "rect" in region:
                coords = region["rect"]
                if not (isinstance(coords, list) and len(coords) == 4):
                    print("Skipping invalid region (rect format):", region)
                    continue
                x1, y1, x2, y2 = coords
            else:
                try:
                    x1 = float(region.get("x1", 0))
                    y1 = float(region.get("y1", 0))
                    x2 = float(region.get("x2", 0))
                    y2 = float(region.get("y2", 0))
                except Exception as e:
                    print("Region conversion error:", region, e)
                    continue

            # Koordinatların geçerli olup olmadığını kontrol edin:
            if x2 <= x1 or y2 <= y1:
                print("Skipping invalid region (x2<=x1 veya y2<=y1):", region)
                continue

            rect = fitz.Rect(x1, y1, x2, y2)
            try:
                page_num = int(region.get("page", 0))
            except Exception as e:
                print("Region page conversion error:", region, e)
                continue

            try:
                orig_page = orig_doc[page_num]
                # Original sayfadan bu bölgenin görüntüsünü al
                pix = orig_page.get_pixmap(clip=rect)
                img_bytes = pix.tobytes("png")
                # Restore işlemi yapılacak sayfayı al
                doc_page = doc[page_num]
                # İlk olarak, blur yapılan bölgeyi beyazla kapat
                doc_page.draw_rect(rect, fill=(1, 1, 1))
                # Sonra, original görüntüyü ekle
                doc_page.insert_image(rect, stream=img_bytes)
            except Exception as e:
                print("Error processing region", region, e)
                continue
        
        # Yeni PDF'yi output_pdf_path'e kaydet
        doc.save(output_pdf_path)
        doc.close()
        orig_doc.close()
        return True
    except Exception as e:
        print("restore_original_fields error:", e)
        return False

def merge_and_restore(input_pdf_path, anonymized_data, output_pdf_path):
    """
    input_pdf_path: reviewed PDF (hakem değerlendirmesi eklenmiş)
    anonymized_data: JSON verisi (blur yapılmış alanlar)
    output_pdf_path: final PDF (orijinal bilgileri geri yüklenmiş)
    """
    # PyMuPDF ile unblur / restore logic vs.
    try:
        doc = fitz.open(input_pdf_path)
        # restore logic ...
        doc.save(output_pdf_path)
        doc.close()
        return True
    except Exception as e:
        print("merge_and_restore error:", e)
        return False


def merge_review_comments(input_pdf_path, review_text, output_pdf_path):
    """
    input_pdf_path -> Mevcut (var olan) anonim PDF
    review_text -> Hakemin değerlendirmesi
    output_pdf_path -> Yeni oluşturulacak "Değerlendirilmiş PDF" dosyası
    """
    import fitz
    import os

    try:
        # 1) Girdi olarak var olan PDF'yi aç
        doc = fitz.open(input_pdf_path)

        # 2) Gerekirse klasörü oluştur (media\reviewed). 
        os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)

        # 3) Yeni sayfa ekleyip review_text'i yazalım (daha gelişmiş formatlama da yapılabilir).
        page = doc.new_page(-1)
        page.insert_text((72, 72), review_text, fontsize=12)

        # 4) Yeni dosya oluştur (output_pdf_path)
        doc.save(output_pdf_path)
        doc.close()
        return True
    except Exception as e:
        print("merge_review_comments error:", e)
        return False
