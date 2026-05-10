"""图片检测和工具函数"""

import base64
import hashlib
from typing import Tuple


def detect_images(content) -> Tuple[str, list[str]]:
    """
    从用户消息中分离文本和图片。
    返回: (纯文本内容, base64图片URI列表)
    """
    if isinstance(content, str):
        return content, []

    image_uris = []
    text_parts = []

    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "image_url":
                    url = part.get("image_url", {}).get("url", "")
                    if url:
                        image_uris.append(url)
                elif part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
            elif isinstance(part, str):
                text_parts.append(part)

    return " ".join(text_parts), image_uris


def get_image_hash(data_uri: str) -> str:
    """生成图片的 MD5 哈希用于缓存"""
    return hashlib.md5(data_uri.encode()).hexdigest()


def decode_base64_image(data_uri: str) -> Tuple[bytes, str]:
    """
    从 data URI 中解码 base64 图片数据。
    返回: (图片字节数据, MIME类型)
    """
    if not data_uri.startswith("data:"):
        raise ValueError("不是有效的 data URI")

    header, encoded = data_uri.split(",", 1)
    mime_type = header.split(":")[1].split(";")[0] if ":" in header else "image/png"
    return base64.b64decode(encoded), mime_type
