"""文生图工具 — 作为标准 Tool 供 LLM 调用"""

import os
import requests
import time

MODELSCOPE_API_KEY = os.getenv("MODELSCOPE_API_KEY", "")
BASE = "https://api-inference.modelscope.cn"


def generate_image(prompt: str, size: str = "1024x1024", steps: int = 30) -> str:
    """由 LLM 调用的生图工具"""
    if not MODELSCOPE_API_KEY:
        return "错误: 未配置 MODELSCOPE_API_KEY，无法生图"

    model = os.getenv("IMAGE_GEN_MODEL", "Tongyi-MAI/Z-Image-Turbo")

    try:
        # 提交异步任务
        headers = {
            "Authorization": f"Bearer {MODELSCOPE_API_KEY}",
            "Content-Type": "application/json",
            "X-ModelScope-Async-Mode": "true",
        }
        resp = requests.post(
            f"{BASE}/v1/images/generations",
            headers=headers,
            json={"model": model, "prompt": prompt, "size": size, "steps": steps},
            timeout=30,
        )
        resp.raise_for_status()
        task_id = resp.json()["task_id"]

        # 轮询等待结果（超时保护: 最多 60s）
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
                    return f"生图成功! 图片URL: {images[0]}"
                return "生图完成但未返回图片"
            elif data.get("task_status") == "FAILED":
                return f"生图失败: {data.get('task_error', '未知错误')}"
            time.sleep(3)

        return f"生图超时(task_id: {task_id})，请稍后通过 /api/images/generations/{task_id} 查询"
    except requests.Timeout:
        return "生图失败: API 请求超时，请稍后重试"
    except Exception as e:
        return f"生图失败: {str(e)}"


tool_def = {
    "type": "function",
    "function": {
        "name": "generate_image",
        "description": "根据文字描述生成图片。当用户要求画图、生成图片、创作图像时使用此工具。",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "图片描述/提示词，用中文详细描述想要的画面",
                },
                "size": {
                    "type": "string",
                    "description": "图片尺寸，如 1024x1024, 1024x768, 768x1024",
                },
                "steps": {
                    "type": "integer",
                    "description": "采样步数，默认30。步数越多质量越高但越慢",
                },
            },
            "required": ["prompt"],
        },
    },
    "exec_mode": "async",
}
