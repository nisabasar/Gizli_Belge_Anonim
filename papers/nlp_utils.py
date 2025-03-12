import fitz  # PyMuPDF
import re
import spacy
from collections import Counter

# spaCy modelini yükleyin (en_core_web_sm modelinin kurulu olduğundan emin olun)
nlp = spacy.load("en_core_web_sm")

def extract_keywords_from_pdf_advanced(pdf_path, top_n=10):
    text_content = ""
    try:
        doc = fitz.open(pdf_path)
        text_content = "\n".join(page.get_text("text") for page in doc)
        doc.close()
    except Exception as e:
        print("PDF metni çıkarma hatası:", e)
        return []
    
    text_content = re.sub(r'\s+', ' ', text_content)
    candidate_headers = ["keywords", "index terms", "anahtar kelimeler", "keywords-component"]
    abstract_pattern = re.compile(r'(?i)(Abstract|Özet)(.*?)(Introduction|Giriş)', re.DOTALL)
    abstract_match = abstract_pattern.search(text_content)
    if abstract_match:
        abstract_text = abstract_match.group(2)
    else:
        abstract_text = text_content
    
    keywords_text = None
    for header in candidate_headers:
        pattern = re.compile(re.escape(header) + r"[\s:\-–—]+(.+?)(?=\s+[A-Z0-9]+\s*\.|$)", re.IGNORECASE)
        m = pattern.search(abstract_text)
        if m:
            keywords_text = m.group(1).strip()
            break

    if keywords_text:
        keywords_text = re.split(r'\s+[A-Z0-9]+\s*\.', keywords_text)[0]
        keywords = [kw.strip() for kw in re.split(r'[;,]', keywords_text) if kw.strip()]
        keywords = [kw for kw in keywords if kw.lower() != "component"]
        return keywords

    doc_nlp = nlp(text_content)
    noun_chunks = [chunk.text.strip() for chunk in doc_nlp.noun_chunks if len(chunk.text.strip()) > 2]
    freq = Counter(noun_chunks)
    top_keywords = [kw for kw, count in freq.most_common(top_n)]
    return top_keywords
