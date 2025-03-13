import re
import fitz  # PyMuPDF
import spacy
from PIL import Image, ImageFilter
import io
import shutil

# İngilizce spaCy modelini yükleyin (kurulu olduğundan emin olun: python -m spacy download en_core_web_sm)
nlp = spacy.load("en_core_web_sm")

# E-posta adreslerini bulmak için regex
EMAIL_REGEX = r'[\w\.-]+@[\w\.-]+\.\w+'

# Anonimleştirme dışı bırakılacak bölüm başlıkları (örneğin, "Introduction", "Related Works", "References", "Acknowledgments")
SKIP_SECTIONS = ["introduction", "related works", "references", "acknowledgments"]

def is_skip_section(line):
    """Satırın, anonimleştirme dışı bırakılacak bir bölüm başlığıyla başladığını kontrol eder."""
    line_lower = line.strip().lower()
    return any(line_lower.startswith(section) for section in SKIP_SECTIONS)

def get_blurred_image_from_rect(page, rect, blur_radius=5):
    """
    Belirtilen dikdörtgen (rect) alanını sayfadan alır, Pillow ile blur uygular
    ve PNG formatında bir byte stream olarak döndürür.
    """
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
    PDF belgesinin orijinal formatını koruyarak, yalnızca hassas alanları bulanıklaştırır.
    - input_pdf_path: Orijinal PDF dosya yolu.
    - output_pdf_path: Anonimleştirilmiş PDF kaydedilecek yol.
    - options: {
           'anonymize_name': bool,         # Yazar ad-soyad
           'anonymize_contact': bool,      # E-posta, telefon vb.
           'anonymize_institution': bool   # Kurum bilgileri
         }
    İşlem, özellikle PDF'in ilk sayfası üzerinde yapılır (yazar bilgileri genellikle burada bulunur).
    """
    if options is None:
        options = {
            'anonymize_name': True,
            'anonymize_contact': True,
            'anonymize_institution': True
        }

    doc = fitz.open(input_pdf_path)
    # Genellikle yazar bilgileri ilk sayfada yer alır; bu yüzden sadece sayfa 0'ı işleyelim.
    page = doc[0]
    text = page.get_text("text")
    # SpaCy ile metni analiz et
    spacy_doc = nlp(text)

    # İşlenen alanları takip etmek için liste
    processed_rects = []

    # İşlemi sadece sayfanın üst kısmında (örneğin y < 300) yapalım
    TOP_THRESHOLD = 300

    # PERSON (yazar adı) ve ORG (kurum) varlıkları için
    for ent in spacy_doc.ents:
        if ent.start_char >= ent.end_char:
            continue  # Boş varlıklar
        # Eğer satır skip edilmemişse (genellikle üst kısımda)
        if ent.label_ == "PERSON" and options.get('anonymize_name'):
            rects = page.search_for(ent.text)
            for rect in rects:
                if rect.y0 < TOP_THRESHOLD and not any(rect.intersects(r) for r in processed_rects):
                    img_stream = get_blurred_image_from_rect(page, rect, blur_radius=5)
                    page.insert_image(rect, stream=img_stream)
                    processed_rects.append(rect)
        elif ent.label_ == "ORG" and options.get('anonymize_institution'):
            rects = page.search_for(ent.text)
            for rect in rects:
                if rect.y0 < TOP_THRESHOLD and not any(rect.intersects(r) for r in processed_rects):
                    img_stream = get_blurred_image_from_rect(page, rect, blur_radius=5)
                    page.insert_image(rect, stream=img_stream)
                    processed_rects.append(rect)

    # E-posta adreslerini regex ile bul ve bulanıklaştır
    for match in re.finditer(EMAIL_REGEX, text):
        email = match.group(0)
        rects = page.search_for(email)
        for rect in rects:
            if rect.y0 < TOP_THRESHOLD and not any(rect.intersects(r) for r in processed_rects):
                img_stream = get_blurred_image_from_rect(page, rect, blur_radius=5)
                page.insert_image(rect, stream=img_stream)
                processed_rects.append(rect)

    doc.save(output_pdf_path)
    doc.close()
    return True

def merge_review_comments(anon_pdf_path, review_text, final_path):
    """
    Anonimleştirilmiş PDF'in sonuna hakem yorumlarını ekler.
    Yeni bir sayfa ekleyerek yorum metnini ekler.
    """
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

def restore_original_fields(anon_pdf_path, original_pdf_path):
    """
    Demo amaçlı: Orijinal PDF'i anonim PDF'in üzerine kopyalar.
    Gerçek uygulamada, yalnızca belirli alanların geri yüklenmesi için gelişmiş işlemler uygulanmalıdır.
    """
    try:
        shutil.copyfile(original_pdf_path, anon_pdf_path)
        return True
    except Exception as e:
        print("Orijinal bilgileri geri yükleme hatası:", e)
        return False
