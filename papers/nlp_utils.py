import fitz  # PyMuPDF
import re
import spacy
from collections import Counter

# spaCy modelini yükleyin (ilk kullanımda "en_core_web_sm" modelinin yüklü olduğundan emin olun)
nlp = spacy.load("en_core_web_sm")

def extract_keywords_from_pdf_advanced(pdf_path, top_n=10):
    """
    PDF'in tamamını tarar ve "Keywords", "Index Terms", "Anahtar Kelimeler",
    "Keywords-component" gibi farklı başlık ifadelerini tespit eder.
    
    1. Belgedeki tüm metni çıkarır ve Abstract/Özet bölümünde bu başlık ifadelerini arar.
    2. Eğer bu kısım bulunursa, header ifadesinden sonraki metni yakalar, 
       sonrasında olası bölüm başlıklarını (örneğin "I. INTRODUCTION", "1." vb.) 
       keser ve virgül/noktalı virgülle ayrılmış anahtar kelimeleri listeye çevirir.
    3. Eğer header bulunamazsa, yedek olarak tüm metni NLP ile analiz edip noun chunk’lar
       üzerinden basit frekans analizi yapar.
    """
    text_content = ""
    try:
        doc = fitz.open(pdf_path)
        text_content = "\n".join(page.get_text("text") for page in doc)
        doc.close()
    except Exception as e:
        print("PDF metni çıkarma hatası:", e)
        return []
    
    # Fazla boşlukları tek boşluk haline indiriyoruz.
    text_content = re.sub(r'\s+', ' ', text_content)
    
    # Aday anahtar kelime başlıkları (küçük harf duyarlı olmaması için re.IGNORECASE kullanıyoruz)
    candidate_headers = ["keywords", "index terms", "anahtar kelimeler", "keywords-component"]
    
    # Öncelikle Abstract/Özet bölümünü bulmaya çalışalım
    abstract_pattern = re.compile(r'(?i)(Abstract|Özet)(.*?)(Introduction|Giriş)', re.DOTALL)
    abstract_match = abstract_pattern.search(text_content)
    if abstract_match:
        abstract_text = abstract_match.group(2)
    else:
        abstract_text = text_content  # Bulunamazsa tüm metni kullan
    
    keywords_text = None
    for header in candidate_headers:
        # Bu desen, header ifadesinden sonra gelen kısmı yakalar.
        # Desende [\s:\-–—]+ kısmına em dash (—) de eklendi.
        # Lookahead kısmı, bir bölüm başlığı (örneğin "I. " veya "1. ") ya da metnin sonunu belirtir.
        pattern = re.compile(re.escape(header) + r"[\s:\-–—]+(.+?)(?=\s+[A-Z0-9]+\s*\.|$)", re.IGNORECASE)
        m = pattern.search(abstract_text)
        if m:
            keywords_text = m.group(1).strip()
            break

    if keywords_text:
        # Eğer keywords_text içinde bölüm başlığı veya yeni satır varsa, onu temizle
        keywords_text = re.split(r'\s+[A-Z0-9]+\s*\.', keywords_text)[0]
        # Anahtar kelimeler genellikle virgül veya noktalı virgülle ayrılır
        keywords = [kw.strip() for kw in re.split(r'[;,]', keywords_text) if kw.strip()]
        # İstenmeyen ifadeleri filtreleyelim (örneğin "component")
        keywords = [kw for kw in keywords if kw.lower() != "component"]
        return keywords

    # Eğer anahtar kelime kısmı bulunamazsa, tüm metni NLP ile analiz et (yedek yöntem)
    doc_nlp = nlp(text_content)
    noun_chunks = [chunk.text.strip() for chunk in doc_nlp.noun_chunks if len(chunk.text.strip()) > 2]
    freq = Counter(noun_chunks)
    top_keywords = [kw for kw, count in freq.most_common(top_n)]
    return top_keywords
