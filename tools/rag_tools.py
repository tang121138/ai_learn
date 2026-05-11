"""RAG 工具 — LLM 可调用的知识库操作"""
import os
from tools.file_ops import SAFE_BASE_DIR


def search_knowledge(query: str, top_k: int = 5) -> str:
    """搜索知识库"""
    try:
        from backend.rag.rag_service import rag_service
        import asyncio

        async def _search():
            return await rag_service.search(query, top_k=top_k)

        results = asyncio.run(_search())
        if not results:
            return "知识库中未找到相关内容。"

        lines = [f"找到 {len(results)} 条相关内容:"]
        for i, r in enumerate(results, 1):
            src = r["metadata"].get("filename", "unknown")
            lines.append(f"\n[{i}] (来源: {src}, 相似度: {r['similarity']:.2f})")
            lines.append(r["text"][:500])
        return "\n".join(lines)
    except Exception as e:
        return f"知识库搜索失败: {e}"


def upload_document(filepath: str, filename: str | None = None) -> str:
    """上传文档到知识库"""
    try:
        real = os.path.realpath(os.path.expanduser(filepath))
        if not real.startswith(SAFE_BASE_DIR):
            return f"错误: 文件路径不在安全目录内: {filepath}"
        if not os.path.isfile(real):
            return f"错误: 文件不存在: {filepath}"

        from backend.rag.rag_service import rag_service
        import asyncio

        async def _upload():
            return await rag_service.upload_document(real, "system", filename)

        result = asyncio.run(_upload())
        return (f"文档已成功上传到知识库:\n"
                f"  - 文件: {result['filename']}\n"
                f"  - 文档ID: {result['doc_id']}\n"
                f"  - 分块数: {result['chunks']}")
    except Exception as e:
        return f"上传文档失败: {e}"


def list_documents() -> str:
    """列出知识库中的所有文档"""
    try:
        from backend.rag.rag_service import rag_service
        import asyncio

        async def _list():
            return await rag_service.list_documents("system")

        docs = asyncio.run(_list())
        if not docs:
            return "知识库中没有文档。"

        lines = [f"知识库共 {len(docs)} 个文档:"]
        for d in docs:
            lines.append(f"  - [{d['doc_id'][:12]}...] {d['filename']} ({d['chunk_count']} chunks)")
        return "\n".join(lines)
    except Exception as e:
        return f"列出文档失败: {e}"


def delete_document(doc_id: str) -> str:
    """从知识库删除文档"""
    try:
        from backend.rag.rag_service import rag_service
        import asyncio

        async def _delete():
            return await rag_service.delete_document(doc_id, "system")

        asyncio.run(_delete())
        return f"文档 {doc_id[:12]}... 已从知识库删除。"
    except Exception as e:
        return f"删除文档失败: {e}"


tool_defs = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "搜索知识库，查找与问题相关的文档片段。当用户询问关于已上传文档的内容时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回结果数量，默认5",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upload_document",
            "description": "上传文档到知识库。支持 PDF、TXT、MD、DOCX、Python等格式。",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "文件路径",
                    },
                    "filename": {
                        "type": "string",
                        "description": "文件名（可选）",
                    },
                },
                "required": ["filepath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_documents",
            "description": "列出知识库中已上传的所有文档",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_document",
            "description": "从知识库中删除指定文档",
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string", "description": "文档ID"},
                },
                "required": ["doc_id"],
            },
        },
    },
]
