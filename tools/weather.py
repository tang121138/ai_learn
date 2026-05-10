import requests


def get_weather(city: str) -> str:
    """查询指定城市的实时天气（使用免费 API）"""
    try:
        url = f"https://wttr.in/{city}?format=%C+%t&lang=zh"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.text.strip()
        else:
            return f"无法获取 {city} 的天气"
    except Exception as e:
        return f"天气查询失败: {str(e)}"


tool_def = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "查询指定城市的当前天气情况",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名称，例如：北京、上海、New York",
                }
            },
            "required": ["city"],
        },
    },
}
