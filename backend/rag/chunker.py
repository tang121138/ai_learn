"""文档分块 — 递归字符分割"""
import os

from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.rag.config import CHUNK_SIZE, CHUNK_OVERLAP


def get_chunker(file_extension: str = ".txt") -> RecursiveCharacterTextSplitter:
    separators = {
        ".py": ["\nclass ", "\ndef ", "\n    def ", "\n\n", "\n", " ", ""],
        ".md": ["\n## ", "\n### ", "\n\n", "\n", " ", ""],
        ".json": ["\n  ", "\n}", "\n]", "\n", " ", ""],
        ".go": ["\nfunc ", "\ntype ", "\n\n", "\n", " ", ""],
        ".java": ["\nclass ", "\n    public ", "\n    private ", "\n\n", "\n", " ", ""],
    }
    default = ["\n\n", "\n", "。", ".", " ", ""]

    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=separators.get(file_extension, default),
        length_function=len,
        add_start_index=True,
    )


def chunk_document(text: str, filename: str) -> list[dict]:
    ext = os.path.splitext(filename)[1].lower()
    splitter = get_chunker(ext)
    chunks = splitter.create_documents([text])
    return [
        {"text": chunk.page_content, "index": chunk.metadata.get("start_index", i)}
        for i, chunk in enumerate(chunks)
    ]
