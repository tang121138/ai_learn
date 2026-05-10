"""图表生成工具 — 使用 matplotlib 生成柱状图/折线图/饼图/散点图"""
import os
import uuid
from backend.logger import get_logger

logger = get_logger("tool.chart")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    logger.warning("matplotlib 未安装，图表生成不可用")

UPLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

API_HOST = os.getenv("API_HOST", "http://localhost:9090")


def generate_chart(chart_type: str, data: str, title: str = "", x_label: str = "",
                   y_label: str = "") -> str:
    """生成图表并保存为图片。

    Args:
        chart_type: 图表类型: bar(柱状图), line(折线图), pie(饼图), scatter(散点图)
        data: JSON 格式数据，格式: [{"label":"A","value":10},{"label":"B","value":20}]
              饼图用 label+value；散点图需要 x,y 字段
        title: 图表标题
        x_label: X轴标签
        y_label: Y轴标签
    """
    if not HAS_MATPLOTLIB:
        return "错误: matplotlib 未安装，无法生成图表。请运行: pip install matplotlib"

    import json
    try:
        points = json.loads(data)
        if not isinstance(points, list) or len(points) == 0:
            return "错误: 数据格式不正确，应为非空 JSON 数组"
    except json.JSONDecodeError as e:
        return f"错误: 数据 JSON 解析失败: {e}"

    try:
        fig, ax = plt.subplots(figsize=(8, 5))

        if chart_type == "bar":
            labels = [p.get("label", str(i)) for i, p in enumerate(points)]
            values = [p.get("value", 0) for p in points]
            ax.bar(labels, values, color="steelblue")
        elif chart_type == "line":
            labels = [p.get("label", str(i)) for i, p in enumerate(points)]
            values = [p.get("value", 0) for p in points]
            ax.plot(labels, values, marker="o", color="steelblue")
        elif chart_type == "pie":
            labels = [p.get("label", str(i)) for i, p in enumerate(points)]
            values = [p.get("value", 0) for p in points]
            ax.pie(values, labels=labels, autopct="%1.1f%%")
            ax.axis("equal")
        elif chart_type == "scatter":
            x_vals = [p.get("x", p.get("value", 0)) for p in points]
            y_vals = [p.get("y", p.get("value", 0)) for p in points]
            ax.scatter(x_vals, y_vals, color="steelblue")
        else:
            plt.close()
            return f"错误: 不支持的图表类型: {chart_type}。支持: bar, line, pie, scatter"

        if chart_type != "pie":
            if x_label:
                ax.set_xlabel(x_label)
            if y_label:
                ax.set_ylabel(y_label)
        if title:
            ax.set_title(title)

        fig.tight_layout()
        filename = f"chart_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join(UPLOADS_DIR, filename)
        fig.savefig(filepath, dpi=100)
        plt.close(fig)

        url = f"{API_HOST}/uploads/{filename}"
        logger.info(f"图表已生成: type={chart_type} title={title[:30]} file={filename}")
        return f"图表已生成! 图片URL: {url}"
    except Exception as e:
        try:
            plt.close()
        except Exception:
            pass
        return f"图表生成失败: {e}"


tool_def = {
    "type": "function",
    "function": {
        "name": "generate_chart",
        "description": "根据数据生成可视化图表（柱状图、折线图、饼图、散点图），保存为图片。当用户要求画图表、数据可视化时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "description": "图表类型: bar(柱状图), line(折线图), pie(饼图), scatter(散点图)",
                    "enum": ["bar", "line", "pie", "scatter"],
                },
                "data": {
                    "type": "string",
                    "description": "JSON 格式的数据数组，每项含 label 和 value 字段。示例: [{\"label\":\"苹果\",\"value\":10},{\"label\":\"香蕉\",\"value\":20}]",
                },
                "title": {
                    "type": "string",
                    "description": "图表标题",
                },
                "x_label": {
                    "type": "string",
                    "description": "X轴标签（饼图不需要）",
                },
                "y_label": {
                    "type": "string",
                    "description": "Y轴标签（饼图不需要）",
                },
            },
            "required": ["chart_type", "data"],
        },
    },
}
