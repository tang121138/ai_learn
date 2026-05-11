"""知识库 API"""
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from backend.middleware.auth import get_current_user
from backend.rag.rag_service import rag_service
from backend.logger import get_logger

logger = get_logger("knowledge")
router = APIRouter(prefix="/api/knowledge", tags=["知识库"])

UPLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")


@router.post("/upload")
async def upload_knowledge(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """上传文档到知识库"""
    if not file.filename:
        raise HTTPException(400, "缺少文件名")
    ext = os.path.splitext(file.filename)[1].lower()
    allowed = {".pdf", ".txt", ".md", ".docx", ".py", ".json", ".yaml", ".yml"}
    if ext not in allowed:
        raise HTTPException(400, f"不支持的文件格式: {ext}")

    filename = f"{uuid.uuid4().hex}_{file.filename}"
    filepath = os.path.join(UPLOADS_DIR, filename)
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    try:
        result = await rag_service.upload_document(filepath, user["id"], file.filename)
        return result
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        logger.error(f"上传文档失败: {e}")
        raise HTTPException(500, f"处理文档失败: {e}")


@router.post("/search")
async def search_knowledge(
    body: dict,
    user: dict = Depends(get_current_user),
):
    """搜索知识库"""
    query = body.get("query", "")
    top_k = int(body.get("top_k", 5))
    if not query:
        raise HTTPException(400, "缺少查询内容")
    return await rag_service.search(query, user["id"], top_k)


@router.get("/documents")
async def list_my_documents(user: dict = Depends(get_current_user)):
    """列出当前用户的所有文档"""
    return await rag_service.list_documents(user["id"])


@router.delete("/documents/{doc_id}")
async def delete_my_document(doc_id: str, user: dict = Depends(get_current_user)):
    await rag_service.delete_document(doc_id, user["id"])
    return {"deleted": doc_id}
