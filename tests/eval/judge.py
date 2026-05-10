"""LLM-as-Judge: 使用强模型作为裁判评估回复质量"""
import json
import os
from openai import OpenAI


def _get_judge_client() -> OpenAI:
    api_key = os.getenv("DEEPSEEK_API_KEY", os.getenv("MODELSCOPE_API_KEY", ""))
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api-inference.modelscope.cn/v1")
    return OpenAI(api_key=api_key, base_url=base_url)


JUDGE_PROMPT = """你是 AI 评测裁判。根据以下标准对 Agent 回复打分 (1-5):

评分标准:
- 5: 完全满足要求，信息准确，表达清晰
- 4: 基本满足要求，有小瑕疵
- 3: 部分满足要求，遗漏了重要信息
- 2: 大部分不满足，有明显错误
- 1: 完全答非所问或存在严重幻觉

用户问题: {question}
预期描述: {expectation}
Agent 回复: {response}

请输出 JSON 格式: {"score": <1-5>, "reasoning": "<简要理由>"}"""


def judge_response(question: str, response: str, expectation: str = "",
                   model_id: str | None = None) -> dict:
    """
    使用 LLM 裁判评估 Agent 回复。
    返回: {"score": 0-1, "raw_score": 1-5, "reasoning": "..."}
    失败时返回默认值，不会抛异常。
    """
    if not response.strip():
        return {"score": 0.0, "raw_score": 1, "reasoning": "回复为空"}

    prompt = JUDGE_PROMPT.format(
        question=question,
        expectation=expectation or "准确回答用户问题",
        response=response[:3000],
    )

    try:
        client = _get_judge_client()
        judge_model = model_id or os.getenv("JUDGE_MODEL", "deepseek-v4-flash")
        completion = client.chat.completions.create(
            model=judge_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
        )
        raw = completion.choices[0].message.content or "{}"
        # 容错: 提取第一个 JSON 对象
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw
        result = json.loads(raw)
        raw_score = max(1, min(5, int(result.get("score", 3))))
        return {
            "score": (raw_score - 1) / 4.0,  # 归一化到 0-1
            "raw_score": raw_score,
            "reasoning": result.get("reasoning", ""),
        }
    except Exception:
        return {"score": 0.5, "raw_score": 3, "reasoning": "裁判模型调用失败，使用默认分"}
