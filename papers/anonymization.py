# papers/anonymization.py
import fitz  # PyMuPDF
import re

def anonymize_pdf(input_path, output_path, options):
    """
    input_path: Orijinal PDF dosyasının yolu.
    output_path: Anonimleştirilmiş PDF'nin kaydedileceği yol.
    options: AnonymizeOptionsForm'dan alınan seçimler (dict biçiminde) 
             Örnek: {"anonymize_name": True, "anonymize_contact": False, "anonymize_institution": True}
    
    Bu fonksiyon, PDF'in her sayfasını açar, seçili seçeneklere göre metni redakte eder 
    (örneğin, yazar adını, e-posta adreslerini, kurum adlarını maskeler) ve 
    düzenlenmiş metinle yeni bir PDF dosyası kaydeder.
    
    Not: PDF'lerde metin düzenleme işlemleri karmaşık olabilir. Bu örnek,
    sayfa içeriğini basitleştirilmiş şekilde redakte edip, yeni metni sayfaya ekler.
    """
    try:
        doc = fitz.open(input_path)
        for page in doc:
            # Sayfadaki tüm metni alıyoruz
            text = page.get_text("text")
            # Seçilen seçeneklere göre redaksiyon yapıyoruz:
            if options.get("anonymize_name"):
                # Basit bir örnek: Büyük harfle başlayan iki kelimeden oluşan isimleri "****" ile değiştiriyoruz.
                text = re.sub(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', "****", text)
            if options.get("anonymize_contact"):
                # E-posta adreslerini redakte ediyoruz
                text = re.sub(r'\S+@\S+', "****", text)
            if options.get("anonymize_institution"):
                # Örneğin "University", "Institute", "College" gibi ifadeleri maskeliyoruz
                text = re.sub(r'\b(University|Institute|College)\b', "****", text)
            # Sayfanın mevcut içeriğini temizleyip, redakte edilmiş metni yeniden ekliyoruz.
            page.clean_contents()
            # Yeni metni sayfanın üst sol köşesine ekliyoruz. (Font, boyut, konum vb. ayarlanabilir)
            page.insert_text((72, 72), text, fontsize=12)
        doc.save(output_path)
        doc.close()
        return True
    except Exception as e:
        print("Anonimleştirme sırasında hata:", e)
        return False

def merge_review_comments(pdf_path, comments, output_path):
    """
    Bu fonksiyon, verilen PDF dosyasının sonuna hakem yorumlarını ekler.
    Basit bir örnek uygulamadır: PDF'e yeni bir sayfa ekler ve 
    verilen yorumları bu sayfaya yazar.
    
    pdf_path: Orijinal PDF dosyasının yolu.
    comments: Eklenecek yorumlar (string).
    output_path: Yeni PDF dosyasının kaydedileceği yol.
    """
    try:
        doc = fitz.open(pdf_path)
        # Yeni bir sayfa ekliyoruz
        page = doc.new_page(-1)
        # Yorum metnini sayfanın üst kısmına ekliyoruz.
        page.insert_text((72, 72), comments, fontsize=12)
        doc.save(output_path)
        doc.close()
        return True
    except Exception as e:
        print("Review comments merge error:", e)
        return False
