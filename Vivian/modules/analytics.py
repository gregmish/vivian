import os
import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ExifTags
from io import BytesIO
from docx import Document
from langdetect import detect_langs, DetectorFactory, LangDetectException
import logging
from typing import Optional, Dict, Any, List, Union

DetectorFactory.seed = 0  # For deterministic language detection

# ========= Future-Ready: Placeholders for Plug-in/Extension ==========

def custom_nlp_hooks(text: str, hooks: Optional[List[Any]] = None) -> Dict[str, Any]:
    """
    Run custom NLP hooks (plugin pattern). 
    Each hook should be a callable: hook(text) -> Dict[str, Any]
    """
    results = {}
    if hooks:
        for hook in hooks:
            try:
                result = hook(text)
                results[hook.__name__] = result
            except Exception as e:
                results[hook.__name__] = f"Error: {e}"
    return results

def topic_modeling(text: str, num_topics: int = 3) -> List[str]:
    """
    Topic modeling with Gensim or other libraries (placeholder).
    """
    try:
        from gensim import corpora, models
        from gensim.utils import simple_preprocess
        texts = [simple_preprocess(text)]
        dictionary = corpora.Dictionary(texts)
        corpus = [dictionary.doc2bow(t) for t in texts]
        lda = models.LdaModel(corpus, num_topics=num_topics, id2word=dictionary, passes=1)
        topics = lda.print_topics(num_words=3)
        return [t[1] for t in topics]
    except ImportError:
        return []
    except Exception:
        return []

def question_answering(text: str, question: str, qa_func: Optional[Any] = None) -> str:
    """
    Question answering over text using LLM or specialized models if provided.
    """
    if qa_func:
        try:
            return qa_func(text, question)
        except Exception as e:
            return f"QA Error: {e}"
    return "[analytics] No QA function provided."

def semantic_search(text: str, query: str, search_func: Optional[Any] = None) -> Any:
    """
    Semantic search in text using embeddings or LLM, if provided.
    """
    if search_func:
        try:
            return search_func(text, query)
        except Exception as e:
            return f"Semantic search error: {e}"
    return []

# ========== Language Detection, Entities, Sentiment ==========

def detect_language(text: str) -> Dict[str, Any]:
    """Return detected language and confidence, or unknown."""
    try:
        langs = detect_langs(text[:1000])
        if langs:
            return {"language": langs[0].lang, "confidence": float(langs[0].prob)}
        else:
            return {"language": "unknown", "confidence": 0.0}
    except (LangDetectException, Exception):
        return {"language": "unknown", "confidence": 0.0}

def analyze_entities(text: str, top_n: int = 10) -> List[Dict[str, Any]]:
    """Extract named entities using spaCy if available."""
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        doc = nlp(text)
        entities = []
        for ent in doc.ents[:top_n]:
            entities.append({"text": ent.text, "label": ent.label_})
        return entities
    except ImportError:
        return []
    except Exception:
        return []

def analyze_sentiment(text: str) -> Dict[str, Any]:
    """Analyze sentiment using TextBlob or spaCy if available."""
    try:
        from textblob import TextBlob
        blob = TextBlob(text)
        return {
            "polarity": blob.sentiment.polarity,
            "subjectivity": blob.sentiment.subjectivity
        }
    except ImportError:
        try:
            import spacy
            nlp = spacy.load("en_core_web_sm")
            doc = nlp(text)
            if hasattr(doc, "sentiment"):
                return {"sentiment": doc.sentiment}
        except Exception:
            pass
        return {"sentiment": "unavailable"}
    except Exception:
        return {"sentiment": "unavailable"}

# ========== Extraction Functions ==========

def extract_text_from_pdf(path: str) -> str:
    """Extract text from a PDF file using PyMuPDF."""
    text = []
    try:
        doc = fitz.open(path)
        for page in doc:
            text.append(page.get_text())
        doc.close()
    except Exception as e:
        logging.error(f"[analytics] PDF extract error: {e}")
    return "\n".join(text)

def extract_text_from_docx(path: str) -> str:
    """Extract text from a Word .docx file."""
    text = []
    try:
        doc = Document(path)
        for para in doc.paragraphs:
            text.append(para.text)
    except Exception as e:
        logging.error(f"[analytics] DOCX extract error: {e}")
    return "\n".join(text)

def extract_text_from_image(path: str, lang: Optional[str] = None) -> str:
    """Extract text from an image file using OCR."""
    try:
        img = Image.open(path)
        if lang:
            return pytesseract.image_to_string(img, lang=lang)
        else:
            return pytesseract.image_to_string(img)
    except Exception as e:
        logging.error(f"[analytics] Image OCR error: {e}")
        return ""

def extract_text_from_txt(path: str) -> str:
    """Extract text from a plain text or markdown file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logging.error(f"[analytics] TXT extract error: {e}")
        return ""

def extract_text_from_file(path: str) -> Dict[str, Any]:
    """Auto-detect file type and extract text."""
    ext = os.path.splitext(path)[-1].lower().lstrip('.')
    text = ""
    error = ""
    if ext in ["txt", "md"]:
        text = extract_text_from_txt(path)
    elif ext == "pdf":
        text = extract_text_from_pdf(path)
    elif ext == "docx":
        text = extract_text_from_docx(path)
    elif ext in ["jpg", "jpeg", "png"]:
        text = extract_text_from_image(path)
    else:
        error = f"Unsupported file type: {ext}"
    return {
        "text": text,
        "error": error,
        "metadata": get_file_metadata(path)
    }

# ========== Summarization (LLM and Extractive) ==========

def summarise_text(
    text: str, 
    max_lines: int = 10, 
    method: str = "simple", 
    llm_func: Optional[Any] = None,
    llm_model: str = "gpt-4"
) -> str:
    """
    Summarize text using a method: 'simple', 'llm', 'llm_extract', etc.
    - llm_func should be a callable that takes a prompt and returns a summary.
    """
    if method == "simple":
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines[:max_lines])
    elif method.startswith("llm"):
        if llm_func:
            prompt = ""
            if method == "llm":
                prompt = f"Summarize the following text in {max_lines} lines or less:\n\n{text}"
            elif method == "llm_extract":
                prompt = f"Extract the most important points from the following text, listing no more than {max_lines} items:\n\n{text}"
            try:
                return llm_func(prompt, model=llm_model)
            except Exception as e:
                return f"[analytics] LLM summarization error: {e}"
        else:
            return "[analytics] No LLM function provided for summarization."
    return "[analytics] Advanced summarization not available."

# ========== Keyword/Entity Extraction ==========

def extract_keywords(text: str, top_n: int = 10) -> List[str]:
    """Extract keywords using spaCy or fallback to naive method."""
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        doc = nlp(text)
        keywords = [chunk.text for chunk in doc.noun_chunks][:top_n]
        return keywords
    except ImportError:
        from collections import Counter
        words = [w for w in text.split() if w.isalpha() and len(w) > 3]
        return [w for w, _ in Counter(words).most_common(top_n)]
    except Exception:
        return []

# ========== File Metadata ==========

def get_file_metadata(path: str) -> dict:
    try:
        stat = os.stat(path)
        ext = os.path.splitext(path)[-1].lower().lstrip('.')
        info = {
            "path": path,
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "modified": stat.st_mtime,
            "extension": ext,
        }
        # PDF page count
        if ext == "pdf":
            try:
                doc = fitz.open(path)
                info["page_count"] = len(doc)
            except Exception:
                info["page_count"] = None
        # Image EXIF
        if ext in ["jpg", "jpeg", "png"]:
            try:
                img = Image.open(path)
                exif_data = img._getexif()
                if exif_data:
                    exif = {
                        ExifTags.TAGS.get(k, k): v
                        for k, v in exif_data.items()
                        if k in ExifTags.TAGS
                    }
                    info["exif"] = exif
                info["image_size"] = img.size
                info["image_mode"] = img.mode
            except Exception:
                pass
        return info
    except Exception:
        return {}

# ========== Batch Processing ==========

def analyze_file(
    path: str,
    summary_lines: int = 10,
    summary_method: str = "simple",
    llm_func: Optional[Any] = None,
    llm_model: str = "gpt-4",
    extract_entities: bool = True,
    extract_sentiment: bool = True,
    nlp_hooks: Optional[List[Any]] = None,
    qa_func: Optional[Any] = None,
    semantic_search_func: Optional[Any] = None,
    topics: bool = True
) -> Dict[str, Any]:
    """
    Full pipeline: text, summary, keywords/entities, sentiment, metadata, plugins/hooks, QA, semantic search, topic modeling.
    """
    info = extract_text_from_file(path)
    text = info.get("text", "")
    analysis = {
        "text": text,
        "summary": summarise_text(
            text, max_lines=summary_lines, method=summary_method, llm_func=llm_func, llm_model=llm_model
        ),
        "keywords": extract_keywords(text),
        "language": detect_language(text),
        "metadata": info.get("metadata", {}),
        "error": info.get("error", "")
    }
    if extract_entities:
        analysis["entities"] = analyze_entities(text)
    if extract_sentiment:
        analysis["sentiment"] = analyze_sentiment(text)
    if topics:
        analysis["topics"] = topic_modeling(text)
    if nlp_hooks:
        analysis["nlp_hooks"] = custom_nlp_hooks(text, nlp_hooks)
    # QA and semantic search are advanced, only run if a function is provided
    if qa_func:
        analysis["question_answering"] = lambda question: question_answering(text, question, qa_func)
    if semantic_search_func:
        analysis["semantic_search"] = lambda query: semantic_search(text, query, semantic_search_func)
    return analysis

def process_files(
    paths: List[str],
    summary_lines: int = 10,
    summary_method: str = "simple",
    llm_func: Optional[Any] = None,
    llm_model: str = "gpt-4",
    extract_entities: bool = True,
    extract_sentiment: bool = True,
    nlp_hooks: Optional[List[Any]] = None,
    qa_func: Optional[Any] = None,
    semantic_search_func: Optional[Any] = None,
    topics: bool = True
) -> List[Dict[str, Any]]:
    """Batch analyze files with advanced NLP."""
    return [
        analyze_file(
            p,
            summary_lines=summary_lines,
            summary_method=summary_method,
            llm_func=llm_func,
            llm_model=llm_model,
            extract_entities=extract_entities,
            extract_sentiment=extract_sentiment,
            nlp_hooks=nlp_hooks,
            qa_func=qa_func,
            semantic_search_func=semantic_search_func,
            topics=topics
        ) for p in paths
    ]

# ========== Advanced: API/GUI Friendly Output ==========

def analyze_file_api(
    path: str,
    summary_lines: int = 10,
    return_full_text: bool = False,
    summary_method: str = "simple",
    llm_func: Optional[Any] = None,
    llm_model: str = "gpt-4",
    extract_entities: bool = True,
    extract_sentiment: bool = True,
    nlp_hooks: Optional[List[Any]] = None,
    qa_func: Optional[Any] = None,
    semantic_search_func: Optional[Any] = None,
    topics: bool = True
) -> Dict[str, Any]:
    """Like analyze_file, but optionally omits full text for API efficiency."""
    result = analyze_file(
        path,
        summary_lines=summary_lines,
        summary_method=summary_method,
        llm_func=llm_func,
        llm_model=llm_model,
        extract_entities=extract_entities,
        extract_sentiment=extract_sentiment,
        nlp_hooks=nlp_hooks,
        qa_func=qa_func,
        semantic_search_func=semantic_search_func,
        topics=topics
    )
    if not return_full_text:
        result["text"] = ""
    return result

# ========== Directory Scanning & Filtering ==========

def scan_directory_for_files(
    directory: str,
    allowed_exts: Optional[List[str]] = None,
    recursive: bool = False
) -> List[str]:
    """Return file paths in directory (optionally filtering by extension)."""
    files = []
    for root, _, filenames in os.walk(directory):
        for fname in filenames:
            ext = os.path.splitext(fname)[-1].lower().lstrip('.')
            if allowed_exts and ext not in allowed_exts:
                continue
            files.append(os.path.join(root, fname))
        if not recursive:
            break
    return files

# ========== CLI/API Helpers ==========

def analytics_help():
    print("""
Vivian Analytics Module:
- analyze_file(path): Extract text, summary (simple/LLM), keywords, language, metadata, sentiment, entities, topics, custom hooks, QA, and semantic search from a file.
- process_files([paths...]): Batch process multiple files.
- extract_text_from_file(path): Auto type-detect and extract text (any supported file).
- summarise_text(text, lines, method, llm_func): Simple or LLM summarization.
- extract_keywords(text): Extracts top keywords or noun phrases.
- analyze_entities(text): Extracts named entities.
- analyze_sentiment(text): Analyzes sentiment from text (TextBlob or spaCy).
- topic_modeling(text): Extracts topics using LDA (if gensim available).
- scan_directory_for_files(directory, exts, recursive): Find files by extension.
- All major errors and issues are returned as part of the result dict.
- API-ready: Results as structured dicts for easy GUI or web integration.
- Custom NLP hooks, QA, and semantic search are supported for future extensibility.
- Advanced summarization, entity extraction, and sentiment analysis can be enabled with external libraries or LLMs.
""")