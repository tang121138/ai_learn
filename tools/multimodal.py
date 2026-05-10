"""多模态图像分析工具 — 图片预处理 + base64 直传魔搭 API

消融实验结论:
- 分辨率上限: 2048x2048 (超过报 400)
- base64 上限: ~132K 字符 (对应 2500px 时 97KB JPEG)
- JPEG 质量: 建议 ≥70，低质量噪声会导致模型拒答
- detail:low 和 extra_body 均非必须
"""

import os
import base64
import uuid
from io import BytesIO
from openai import OpenAI
from PIL import Image

MODELSCOPE_API_KEY = os.getenv("MODELSCOPE_API_KEY", "")
MODELSCOPE_BASE_URL = os.getenv("MODELSCOPE_BASE_URL", "https://api-inference.modelscope.cn/v1")
MULTIMODAL_MODEL = os.getenv("MULTIMODAL_MODEL", "Qwen/Qwen3.5-397B-A17B")
API_HOST = os.getenv("API_HOST", "http://localhost:9090")

UPLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

_session_images: dict[str, list[str]] = {}

# 魔搭 API 图片限制 (消融实验测定)
FRAME_MAX_DIMENSION = 2048   # 分辨率硬上限
FRAME_JPEG_QUALITY = 85      # JPEG 质量，≥70 安全


def _preprocess_image(image_path_or_uri: str) -> str:
    """图片预处理: resize + JPEG压缩 → base64 data URI"""
    if image_path_or_uri.startswith("data:"):
        header, b64 = image_path_or_uri.split(",", 1)
        img_bytes = base64.b64decode(b64)
    elif image_path_or_uri.startswith(API_HOST):
        # 本地 URL → 直接读文件，避免 HTTP 请求死锁
        local = image_path_or_uri.replace(f"{API_HOST}/uploads/", "")
        filepath = os.path.join(UPLOADS_DIR, local)
        with open(filepath, "rb") as f:
            img_bytes = f.read()
    elif image_path_or_uri.startswith("http"):
        import requests
        resp = requests.get(image_path_or_uri, timeout=10)
        img_bytes = resp.content
    else:
        # 本地文件路径
        filepath = image_path_or_uri if os.path.isabs(image_path_or_uri) else os.path.join(UPLOADS_DIR, image_path_or_uri)
        with open(filepath, "rb") as f:
            img_bytes = f.read()

    # resize + JPEG 压缩
    img = Image.open(BytesIO(img_bytes))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > FRAME_MAX_DIMENSION:
        ratio = FRAME_MAX_DIMENSION / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=FRAME_JPEG_QUALITY)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def _save_file(image_path_or_uri: str) -> str:
    """存文件并返回 URL"""
    if image_path_or_uri.startswith("data:"):
        header, b64 = image_path_or_uri.split(",", 1)
        mime = header.split(":")[1].split(";")[0] if ":" in header else "image/png"
        ext = mime.split("/")[-1] or "png"
        img_bytes = base64.b64decode(b64)
    else:
        return image_path_or_uri
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(UPLOADS_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(img_bytes)
    return f"{API_HOST}/uploads/{filename}"


def store_session_images(session_id: str, images: list[str]):
    _session_images[session_id] = []
    for img in images:
        url = _save_file(img)
        _session_images[session_id].append(url)


def clear_session_images(session_id: str):
    _session_images.pop(session_id, None)


def get_session_images(session_id: str) -> list[str]:
    return _session_images.get(session_id, [])


def analyze_image(image_index: int = 0, question: str = "请描述这张图片",
                  session_id: str = "") -> str:
    """LLM 调用的图片分析工具 — 压缩后 base64 直传魔搭 API"""
    import traceback
    from backend.logger import get_logger
    _log = get_logger("tool.multimodal")

    # 查找原始图片
    image_src = None
    if session_id:
        imgs = get_session_images(session_id)
        if 0 <= image_index < len(imgs):
            image_src = imgs[image_index]
    if image_src is None:
        for sid, imgs in _session_images.items():
            if 0 <= image_index < len(imgs):
                image_src = imgs[image_index]
                _log.info(f"从会话 {sid[:8]} 找到图片 {image_index}")
                break

    if image_src is None:
        _log.warning(f"未找到图片 index={image_index}, 缓存会话数={len(_session_images)}")
        return f"错误: 未找到图片索引 {image_index}。请确认已上传图片。"

    _log.info(f"开始预处理图片: {image_src[:80]}...")
    try:
        data_uri = _preprocess_image(image_src)
        _log.info(f"预处理完成, base64 长度={len(data_uri)}")
    except Exception as e:
        _log.error(f"预处理失败: {traceback.format_exc()}")
        return f"图片预处理失败: {e}"

    _log.info(f"调用多模态API: model={MULTIMODAL_MODEL}")
    client = OpenAI(api_key=MODELSCOPE_API_KEY, base_url=MODELSCOPE_BASE_URL)
    try:
        resp = client.chat.completions.create(
            model=MULTIMODAL_MODEL,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": data_uri}},
                {"type": "text", "text": question or "请用中文描述这张图片"},
            ]}],
            max_tokens=2048,
            temperature=0.7,
        )
        if not resp.choices:
            _log.error("API 返回空 choices")
            return "图像分析失败: API 返回空结果"
        msg = resp.choices[0].message
        if msg is None:
            _log.error("message 为 None")
            return "图像分析失败: 模型返回空消息"
        content = msg.content
        _log.info(f"多模态API返回 content长度={len(content or '')}")
        return content if content else "(模型返回空内容，请重试)"
    except Exception as e:
        _log.error(f"API调用失败: {traceback.format_exc()}")
        return f"图像分析失败: {e}"


tool_def = {
    "type": "function",
    "function": {
        "name": "analyze_image",
        "description": "分析用户上传的图片内容。当用户发送图片或询问图片相关问题时使用此工具。",
        "parameters": {
            "type": "object",
            "properties": {
                "image_index": {"type": "integer", "description": "图片索引，0=第一张"},
                "question": {"type": "string", "description": "关于图片的问题"},
                "session_id": {"type": "string", "description": "会话ID，用于精确查找该会话中的图片。由系统自动注入，通常不需要手动传"},
            },
            "required": ["image_index"],
        },
    },
    "exec_mode": "async",
}
