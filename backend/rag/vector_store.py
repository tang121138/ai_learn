"""ChromaDB 向量存储 — 用户级别隔离"""
import os
import chromadb
from chromadb.config import Settings

from backend.rag.config import CHROMA_PERSIST_DIR, TOP_K

COLLECTION_NAME = "agent_knowledge"


class VectorStore:
    def __init__(self):
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def add_documents(self, ids: list[str], texts: list[str],
                      embeddings: list[list[float]], metadatas: list[dict]):
        self._collection.add(ids=ids, documents=texts,
                             embeddings=embeddings, metadatas=metadatas)

    def search(self, query_embedding: list[float], top_k: int = TOP_K,
               user_id: str | None = None) -> list[dict]:
        where = {"user_id": user_id} if user_id else None
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        items = []
        for i in range(len(results["ids"][0])):
            distance = results["distances"][0][i]
            items.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "similarity": 1.0 - distance,
            })
        return items

    def delete_document(self, doc_id: str, user_id: str | None = None):
        where = {"doc_id": doc_id}
        if user_id:
            where["user_id"] = user_id
        self._collection.delete(where=where)

    def list_documents(self, user_id: str) -> list[dict]:
        results = self._collection.get(
            where={"user_id": user_id},
            include=["metadatas"],
        )
        seen: dict[str, dict] = {}
        for meta in results["metadatas"]:
            doc_id = meta.get("doc_id")
            if doc_id and doc_id not in seen:
                seen[doc_id] = {
                    "doc_id": doc_id,
                    "filename": meta.get("filename", "unknown"),
                    "chunk_count": 1,
                    "created_at": meta.get("created_at", ""),
                }
            elif doc_id:
                seen[doc_id]["chunk_count"] += 1
        return list(seen.values())
