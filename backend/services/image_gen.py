"""魔搭生图服务 — 异步提交 + 轮询"""

import time
import requests
from backend.config import MODELSCOPE_API_KEY, MODELSCOPE_BASE_URL
from backend.services.model_manager import model_manager

BASE = "https://api-inference.modelscope.cn"


def submit_image_generation(prompt: str, model_id: str = None, size: str = "1024x1024", steps: int = 30) -> str:
    """提交生图任务，返回 task_id"""
    model = model_id or model_manager.get_image_gen_model()
    headers = {
        "Authorization": f"Bearer {MODELSCOPE_API_KEY}",
        "Content-Type": "application/json",
        "X-ModelScope-Async-Mode": "true",
    }
    data = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "steps": steps,
    }
    resp = requests.post(f"{BASE}/v1/images/generations", headers=headers, json=data, timeout=30)
    resp.raise_for_status()
    return resp.json()["task_id"]


def query_task(task_id: str) -> dict:
    """查询生图任务状态"""
    headers = {
        "Authorization": f"Bearer {MODELSCOPE_API_KEY}",
        "Content-Type": "application/json",
        "X-ModelScope-Task-Type": "image_generation",
    }
    resp = requests.get(f"{BASE}/v1/tasks/{task_id}", headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return {
        "task_id": task_id,
        "status": data.get("task_status", "UNKNOWN"),
        "output_images": data.get("output_images", []),
        "error": data.get("task_error", ""),
    }
