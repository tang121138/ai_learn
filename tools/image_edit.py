"""图像编辑工具 — 根据用户提示词编辑对话上文中的图片

模型: Qwen/Qwen-Image-Edit-2511 (魔搭 API Inference)
复用 image_gen.py 的异步提交+轮询模式
"""

import os
import requests
import time
from backend.logger import get_logger

logger = get_logger("tool.image_edit")

MODELSCOPE_API_KEY = os.getenv("MODELSCOPE_API_KEY", "")
BASE = "https://api-inference.modelscope.cn"
EDIT_MODEL = "Qwen/Qwen-Image-Edit-2511"


def edit_image(prompt: str, image_index: int = 0, steps: int = 40, guidance: float = 4.0) -> str:
    """编辑对话上文中的图片。

    Args:
        prompt: 编辑指令，如 "把背景换成海滩"、"给人物添加帽子"、"将图片变为黑白风格"
        image_index: 引用对话中的第几张图片，0=第一张
        steps: 采样步数 (1-100)，越高越精细但越慢
        guidance: 引导强度 (1.5-20.0)
    """
    if not MODELSCOPE_API_KEY:
        logger.warning("edit_image: API Key 未配置")
        return "错误: 未配置 MODELSCOPE_API_KEY，无法编辑图片"

    from tools.multimodal import get_session_images
    session_images = get_session_images(None)
    if not session_images:
        import tools.multimodal as mm
        for sid, imgs in mm._session_images.items():
            session_images = imgs
            break

    if not session_images or image_index >= len(session_images):
        logger.warning(f"edit_image: 未找到图片 index={image_index}, 可用={len(session_images or [])}")
        return f"错误: 未找到可编辑的图片 (index={image_index})。请先上传图片再使用编辑功能。"

    image_url = session_images[image_index]
    if image_url.startswith("data:"):
        return "错误: 不支持 base64 图片，请先上传图片文件"

    logger.info(f"edit_image: prompt={prompt[:80]} image={image_url[:60]} steps={steps}")
    try:
        headers = {
            "Authorization": f"Bearer {MODELSCOPE_API_KEY}",
            "Content-Type": "application/json",
            "X-ModelScope-Async-Mode": "true",
        }
        payload = {
            "model": EDIT_MODEL,
            "prompt": prompt,
            "image_url": [image_url],
            "steps": steps,
            "guidance": guidance,
        }
        resp = requests.post(
            f"{BASE}/v1/images/generations",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        task_id = resp.json()["task_id"]
        logger.info(f"edit_image: 任务已提交 task_id={task_id}")

        start = time.time()
        while time.time() - start < 60:
            result = requests.get(
                f"{BASE}/v1/tasks/{task_id}",
                headers={**headers, "X-ModelScope-Task-Type": "image_generation"},
                timeout=15,
            )
            result.raise_for_status()
            data = result.json()
            if data.get("task_status") == "SUCCEED":
                images = data.get("output_images", [])
                if images:
                    elapsed = time.time() - start
                    logger.info(f"edit_image: 成功 elapsed={elapsed:.1f}s url={images[0][:80]}")
                    return f"图片编辑成功! 结果URL: {images[0]}"
                logger.warning("edit_image: 完成但无图片")
                return "图片编辑完成但未返回图片"
            elif data.get("task_status") == "FAILED":
                err = data.get('task_error', '未知错误')
                logger.error(f"edit_image: 失败 task_id={task_id} error={err}")
                return f"图片编辑失败: {err}"
            time.sleep(3)

        logger.warning(f"edit_image: 超时 task_id={task_id}")
        return f"图片编辑超时(task_id: {task_id})，请稍后通过 /api/images/generations/{task_id} 查询"
    except requests.Timeout:
        logger.error("edit_image: API 请求超时")
        return "图片编辑失败: API 请求超时，请稍后重试"
    except Exception as e:
        logger.error(f"edit_image: 失败 {e}", exc_info=True)
        return f"图片编辑失败: {str(e)}"


tool_def = {
    "type": "function",
    "function": {
        "name": "edit_image",
        "description": "编辑对话上文中的图片。可以修改背景、风格转换、添加/移除元素、调整颜色等。需要先有图片（用户上传或刚生成的）才能使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "编辑指令，用中文详细描述想要的编辑效果。例如: '把背景换成蓝色天空'、'将图片变为油画风格'",
                },
                "image_index": {
                    "type": "integer",
                    "description": "引用对话中的第几张图片，0=第一张(最近上传/生成的)",
                },
                "steps": {
                    "type": "integer",
                    "description": "采样步数 (1-100)，默认40。步数越多质量越高但越慢",
                },
                "guidance": {
                    "type": "number",
                    "description": "引导强度 (1.5-20.0)，默认4.0。越高越贴近提示词",
                },
                "session_id": {
                    "type": "string",
                    "description": "会话ID，用于精确查找该会话中的图片。由系统自动注入，通常不需要手动传",
                },
            },
            "required": ["prompt"],
        },
    },
    "exec_mode": "async",
}
