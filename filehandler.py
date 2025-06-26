import os
import mimetypes
import difflib
from typing import List, Optional, Callable, Dict, Any, Union
import threading

# ========== Supported File Types & Registration System ==========

SUPPORTED_FILE_TYPES: Dict[str, Dict[str, Any]] = {
    "txt":  {"description": "Plain text file", "mime": "text/plain"},
    "md":   {"description": "Markdown file", "mime": "text/markdown"},
    "pdf":  {"description": "PDF document", "mime": "application/pdf"},
    "docx": {"description": "Microsoft Word (Docx)", "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    "png":  {"description": "PNG image", "mime": "image/png"},
    "jpg":  {"description": "JPEG image", "mime": "image/jpeg"},
    "jpeg": {"description": "JPEG image", "mime": "image/jpeg"},
}

FILE_TYPE_HANDLERS: Dict[str, Callable[[str, Optional[dict]], Union[str, dict]]] = {}

MAX_FILE_SIZE_MB = 10  # configurable

def register_file_type(
    ext: str,
    description: str,
    mime: str,
    handler_func: Callable[[str, Optional[dict]], Union[str, dict]]
):
    """Register a new file type and handler at runtime."""
    SUPPORTED_FILE_TYPES[ext] = {"description": description, "mime": mime}
    FILE_TYPE_HANDLERS[ext] = handler_func

def unregister_file_type(ext: str):
    """Remove a file type and its handler."""
    SUPPORTED_FILE_TYPES.pop(ext, None)
    FILE_TYPE_HANDLERS.pop(ext, None)

# ========== File Type Info & Metadata ==========

def supported_file_types() -> List[str]:
    return list(SUPPORTED_FILE_TYPES.keys())

def supported_file_types_info() -> str:
    lines = []
    for ext, info in SUPPORTED_FILE_TYPES.items():
        lines.append(f".{ext}: {info['description']} ({info['mime']})")
    return "\n".join(lines)

def get_file_extension(filepath: str) -> str:
    return os.path.splitext(filepath)[-1].lower().lstrip('.')

def get_mime_type(filepath: str) -> str:
    ext = get_file_extension(filepath)
    if ext in SUPPORTED_FILE_TYPES:
        return SUPPORTED_FILE_TYPES[ext]["mime"]
    mime_type, _ = mimetypes.guess_type(filepath)
    return mime_type or "application/octet-stream"

def get_file_metadata(filepath: str) -> dict:
    """Extract file metadata."""
    try:
        stat = os.stat(filepath)
        return {
            "path": filepath,
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "modified": stat.st_mtime,
            "extension": get_file_extension(filepath),
            "mime_type": get_mime_type(filepath)
        }
    except Exception:
        return {}

# ========== Security & Validation ==========

def is_file_size_safe(filepath: str, max_mb: int = MAX_FILE_SIZE_MB) -> bool:
    """Check if file is within safe size limit."""
    try:
        return os.path.getsize(filepath) <= max_mb * 1024 * 1024
    except Exception:
        return False

def validate_file(filepath: str, ext: str) -> Optional[str]:
    """Security: check size, extension/MIME match, etc."""
    if not is_file_size_safe(filepath):
        return f"[FileHandler] File is too large (>{MAX_FILE_SIZE_MB}MB)."
    mime = get_mime_type(filepath)
    expected_mime = SUPPORTED_FILE_TYPES.get(ext, {}).get("mime")
    if expected_mime and not mime.startswith(expected_mime.split("/")[0]):
        return f"[FileHandler] MIME type ({mime}) does not match extension .{ext} ({expected_mime})."
    return None

# ========== Main Handler (with batch, preview, async, API/GUI) ==========

def handle_file(
    filepath: str,
    config: Optional[dict] = None,
    mode: str = "head",
    as_dict: bool = False,
    preview_chars: int = 3000
) -> Union[str, dict]:
    """
    mode: "head", "tail", "full", "summary", "metadata-only"
    as_dict: return dict for API/GUI, else str for CLI
    """
    ext = get_file_extension(filepath)
    result: dict = {
        "content": "",
        "metadata": get_file_metadata(filepath),
        "error": None,
        "preview_mode": mode
    }

    if not os.path.exists(filepath):
        suggestion = suggest_similar_file(filepath)
        msg = f"[FileHandler] File not found: {filepath}"
        if suggestion:
            msg += f"\nDid you mean: {suggestion} ?"
        result["error"] = msg
        return result if as_dict else msg

    if ext not in supported_file_types():
        close = get_closest_supported_type(ext)
        msg = f"[FileHandler] Unsupported file type: .{ext}"
        if close:
            msg += f"\nDid you mean a supported type like '.{close}'?"
        msg += "\nSupported file types:\n" + supported_file_types_info()
        result["error"] = msg
        return result if as_dict else msg

    # Security check
    sec = validate_file(filepath, ext)
    if sec:
        result["error"] = sec
        return result if as_dict else sec

    # Use registered handler if present
    if ext in FILE_TYPE_HANDLERS:
        try:
            output = FILE_TYPE_HANDLERS[ext](filepath, config)
            if isinstance(output, dict):
                result.update(output)
            else:
                result["content"] = output
        except Exception as e:
            result["error"] = f"[FileHandler] Error in custom handler: {e}"
        return result if as_dict else result["content"] or result["error"] or ""
    
    # Built-in handlers
    try:
        if ext in ["txt", "md"]:
            output = _handle_text_file(filepath, mode=mode, preview_chars=preview_chars)
        elif ext == "pdf":
            output = _handle_pdf_file(filepath, mode=mode, preview_chars=preview_chars)
        elif ext == "docx":
            output = _handle_docx_file(filepath, mode=mode, preview_chars=preview_chars)
        elif ext in ["jpg", "jpeg", "png"]:
            output = _handle_image_file(filepath, config, as_dict=as_dict)
        else:
            output = f"[FileHandler] Unknown supported type: {ext}"
        if isinstance(output, dict):
            result.update(output)
        else:
            result["content"] = output
    except Exception as e:
        result["error"] = f"[FileHandler] Error reading file: {e}"

    if as_dict:
        return result
    if result["error"]:
        return result["error"]
    return result["content"]

def handle_files(
    filepaths: List[str],
    config: Optional[dict] = None,
    mode: str = "head",
    as_dict: bool = False
) -> List[Union[str, dict]]:
    """Batch file handler."""
    return [handle_file(fp, config, mode=mode, as_dict=as_dict) for fp in filepaths]

def handle_file_async(
    filepath: str,
    config: Optional[dict] = None,
    callback: Optional[Callable[[Union[str, dict]], None]] = None,
    mode: str = "head",
    as_dict: bool = False
):
    """Threaded/async file handler."""
    def _worker():
        result = handle_file(filepath, config, mode=mode, as_dict=as_dict)
        if callback:
            callback(result)
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

# ========== Built-in File Handlers ==========

def _handle_text_file(filepath: str, mode: str = "head", preview_chars: int = 3000) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    if mode == "head":
        return content[:preview_chars] + ("\n\n[FileHandler] Content truncated." if len(content) > preview_chars else "")
    elif mode == "tail":
        return (content[-preview_chars:] if len(content) > preview_chars else content)
    elif mode == "full":
        return content
    elif mode == "summary":
        lines = content.splitlines()
        return "\n".join(lines[:15]) + ("\n...[truncated]" if len(lines) > 15 else "")
    elif mode == "metadata-only":
        return "[FileHandler] No content preview. Metadata only."
    else:
        return "[FileHandler] Unknown preview mode."

def _handle_pdf_file(filepath: str, mode: str = "head", preview_chars: int = 3000) -> str:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(filepath)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        if mode == "head":
            return text[:preview_chars] + ("\n\n[FileHandler] PDF content truncated." if len(text) > preview_chars else "")
        elif mode == "full":
            return text
        elif mode == "summary":
            return text[:500]
        elif mode == "metadata-only":
            return "[FileHandler] No content preview. Metadata only."
        else:
            return "[FileHandler] Unknown preview mode."
    except ImportError:
        return "[FileHandler] PyMuPDF (fitz) is not installed. Run: pip install pymupdf"
    except Exception as e:
        return f"[FileHandler] Error reading PDF: {e}"

def _handle_docx_file(filepath: str, mode: str = "head", preview_chars: int = 3000) -> str:
    try:
        import docx
        doc = docx.Document(filepath)
        text = "\n".join([para.text for para in doc.paragraphs])
        if mode == "head":
            return text[:preview_chars] + ("\n\n[FileHandler] DOCX content truncated." if len(text) > preview_chars else "")
        elif mode == "full":
            return text
        elif mode == "summary":
            return text[:500]
        elif mode == "metadata-only":
            return "[FileHandler] No content preview. Metadata only."
        else:
            return "[FileHandler] Unknown preview mode."
    except ImportError:
        return "[FileHandler] python-docx is not installed. Run: pip install python-docx"
    except Exception as e:
        return f"[FileHandler] Error reading DOCX: {e}"

def _handle_image_file(filepath: str, config=None, as_dict=False) -> Union[str, dict]:
    """Image handler: preview (Pillow), OCR if available, metadata."""
    try:
        from PIL import Image
        im = Image.open(filepath)
        info = f"[FileHandler] Image loaded: {filepath} ({im.format}, {im.size[0]}x{im.size[1]})"
        try:
            import pytesseract
            text = pytesseract.image_to_string(im)
            if text.strip():
                snippet = text[:3000] + "\n\n[FileHandler] OCR content truncated." if len(text) > 3000 else text
                if as_dict:
                    return {
                        "content": "",
                        "ocr_text": snippet,
                        "metadata": get_file_metadata(filepath),
                        "error": None
                    }
                return f"{info}\n[FileHandler] OCR Text Preview:\n{snippet}"
            else:
                if as_dict:
                    return {"content": "", "ocr_text": "", "metadata": get_file_metadata(filepath), "error": None}
                return info + "\n[FileHandler] No readable text found using OCR."
        except ImportError:
            if as_dict:
                return {"content": "", "ocr_text": "", "metadata": get_file_metadata(filepath), "error": "OCR not available (install Pillow + pytesseract)."}
            return info + "\n[FileHandler] OCR not available (install Pillow + pytesseract)."
    except ImportError:
        msg = "[FileHandler] Image preview/OCR requires Pillow. Run: pip install pillow"
        if as_dict:
            return {"content": "", "ocr_text": "", "metadata": get_file_metadata(filepath), "error": msg}
        return msg
    except Exception as e:
        msg = f"[FileHandler] Image load error: {e}\nFile saved: {filepath}"
        if as_dict:
            return {"content": "", "ocr_text": "", "metadata": get_file_metadata(filepath), "error": msg}
        return msg

# ========== Advanced Features ==========

def suggest_similar_file(filepath: str, search_dir: Optional[str] = None) -> Optional[str]:
    """Suggest a similar filename in the directory if a file is not found."""
    dirpath = search_dir or os.path.dirname(filepath) or "."
    fname = os.path.basename(filepath)
    try:
        files = os.listdir(dirpath)
        close = difflib.get_close_matches(fname, files, n=1)
        return os.path.join(dirpath, close[0]) if close else None
    except Exception:
        return None

def get_closest_supported_type(ext: str) -> Optional[str]:
    """Suggest the closest supported file type extension."""
    matches = difflib.get_close_matches(ext, supported_file_types(), n=1)
    return matches[0] if matches else None

# ========== Content Analysis & Indexing ==========

def file_content_analysis(filepath: str) -> dict:
    """Analyze text/doc files: word/line count, language, keywords, summary."""
    ext = get_file_extension(filepath)
    result = {}
    if ext in ["txt", "md"]:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            result["line_count"] = content.count("\n") + 1
            result["word_count"] = len(content.split())
            # Optionally use langdetect for language
            try:
                from langdetect import detect
                result["language"] = detect(content[:500])
            except ImportError:
                result["language"] = "unknown (langdetect not installed)"
            except Exception:
                result["language"] = "unknown"
            # Optionally use nltk or similar for keywords/summarization
        except Exception as e:
            result["error"] = str(e)
    # Image EXIF (if Pillow)
    elif ext in ["jpg", "jpeg", "png"]:
        try:
            from PIL import Image
            im = Image.open(filepath)
            result["size"] = im.size
            result["format"] = im.format
            result["mode"] = im.mode
            if hasattr(im, "_getexif"):
                exif = im._getexif()
                result["exif"] = exif
        except Exception as e:
            result["error"] = str(e)
    return result

# ========== File Preview Modes & API Helpers ==========

def get_file_preview(filepath: str, mode: str = "head", preview_chars: int = 3000, as_dict: bool = False) -> Union[str, dict]:
    """Convenience function for file preview."""
    return handle_file(filepath, mode=mode, as_dict=as_dict, preview_chars=preview_chars)

# ========== CLI/GUI/API Helpers & Help ==========

def filehandler_help():
    print("""
FileHandler Usage:
/files                      - List supported file types
>>filename.ext              - Handle (read/preview) a file
File types supported: txt, md, pdf, docx, png, jpg, jpeg

Advanced features:
- Register new file types at runtime with register_file_type()
- Batch handling: handle_files([file1, file2, ...])
- Metadata extraction: get_file_metadata(filepath)
- Preview modes: 'head', 'tail', 'full', 'summary', 'metadata-only'
- Content analysis: file_content_analysis(filepath)
- Asynchronous handling: handle_file_async(filepath, callback=...)
- Returns structured dicts for API/GUI if as_dict=True
- Security: size checks, MIME validation
- Image OCR (if Pillow + pytesseract)
- Suggests similar files if not found
- Plugin hooks for custom handlers

If a dependency is missing (PyMuPDF, python-docx, Pillow, pytesseract),
install it with pip. 
Text and document content is truncated for preview.
""")