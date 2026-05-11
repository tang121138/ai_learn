"""文档加载器 — 支持 PDF, TXT, MD, DOCX"""
import os
from pathlib import Path


def load_document(filepath: str) -> str:
    ext = Path(filepath).suffix.lower()

    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(filepath)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    elif ext in (".docx", ".doc"):
        from docx import Document
        doc = Document(filepath)
        return "\n".join(p.text for p in doc.paragraphs)
    elif ext in (".txt", ".md", ".py", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini"):
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    else:
        # 尝试当文本读取
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except UnicodeDecodeError:
            raise ValueError(f"不支持的文件格式: {ext}")
