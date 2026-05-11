"""RAG 编排服务 — 文档上传 + 语义搜索"""
import os
import uuid
import asyncio
from datetime import datetime, timezone, timedelta

from backend.rag.config import TOP_K, SIMILARITY_THRESHOLD
from backend.rag.embedder import Embedder
from backend.rag.vector_store import VectorStore
from backend.rag.chunker import chunk_document
from backend.rag.document_loader import load_document
from backend.logger import get_logger

logger = get_logger("rag.service")


class RAGService:
    def __init__(self):
        self.embedder = Embedder()
        self.vector_store = VectorStore()

    async def upload_document(self, filepath: str, user_id: str,
                              filename: str | None = None) -> dict:
        if filename is None:
            filename = os.path.basename(filepath)

        # 文件安全校验
        real = os.path.realpath(filepath)
        from tools.file_ops import SAFE_BASE_DIR
        if not real.startswith(SAFE_BASE_DIR):
            raise PermissionError(f"禁止访问安全目录之外的文件: {filepath}")

        doc_id = uuid.uuid4().hex
        text = await asyncio.to_thread(load_document, filepath)
        chunks = chunk_document(text, filename)

        if not chunks:
            return {"doc_id": doc_id, "filename": filename, "chunks": 0}

        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
        texts = [c["text"] for c in chunks]
        now = datetime.now(timezone(timedelta(hours=8))).isoformat()
        metadatas = [{
            "doc_id": doc_id, "chunk_index": i,
            "filename": filename, "user_id": user_id,
            "created_at": now,
        } for i in range(len(chunks))]

        embeddings = await asyncio.to_thread(
            self.embedder.embed_documents, texts)
        self.vector_store.add_documents(ids, texts, embeddings, metadatas)

        logger.info(f"文档已入库: {filename} ({len(chunks)} chunks) user={user_id[:8]}")
        return {"doc_id": doc_id, "filename": filename, "chunks": len(chunks)}

    async def search(self, query: str, user_id: str | None = None,
                     top_k: int = TOP_K) -> list[dict]:
        query_embedding = await self.embedder.embed_query_cached(query)
        results = self.vector_store.search(query_embedding, top_k=top_k, user_id=user_id)
        return [r for r in results if r["similarity"] >= SIMILARITY_THRESHOLD]

    async def delete_document(self, doc_id: str, user_id: str):
        self.vector_store.delete_document(doc_id, user_id)
        logger.info(f"文档已删除: {doc_id}")

    async def list_documents(self, user_id: str) -> list[dict]:
        return self.vector_store.list_documents(user_id)


rag_service = RAGService()
