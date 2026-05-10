"""评测管线配置"""
import os

# 数据目录
DATASETS_DIR = os.path.join(os.path.dirname(__file__), "datasets")
SNAPSHOTS_DIR = os.path.join(os.path.dirname(__file__), "snapshots")

# 评分权重
METRIC_WEIGHTS = {
    "tool_accuracy": 0.40,
    "response_relevance": 0.30,
    "no_hallucination": 0.15,
    "latency": 0.10,
    "format_valid": 0.05,
}

# 延迟阈值 (毫秒)
LATENCY_THRESHOLD_MS = 15000

# LLM-as-Judge 模型 (用更强的模型当裁判)
JUDGE_MODEL = "deepseek-v4-flash"

# 回归检测阈值: 分数下降超过此百分比视为回归
REGRESSION_THRESHOLD = 5.0
