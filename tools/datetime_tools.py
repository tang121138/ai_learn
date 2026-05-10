from datetime import datetime, timedelta, timezone


def get_current_time(timezone_offset: str = "+8") -> str:
    """获取当前日期和时间"""
    try:
        offset_hours = int(timezone_offset)
        tz = timezone(timedelta(hours=offset_hours))
        now = datetime.now(tz)
        return f"{now.strftime('%Y-%m-%d %H:%M:%S %A')} (UTC{offset_hours:+d})"
    except Exception as e:
        return f"获取时间失败: {str(e)}"


def calculate_date(date_str: str, days: int) -> str:
    """日期加减计算"""
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
        result = date + timedelta(days=days)
        return f"{date_str} {'+' if days >= 0 else ''}{days}天 = {result.strftime('%Y-%m-%d')}"
    except ValueError:
        return "日期格式错误，请使用 YYYY-MM-DD 格式"
    except Exception as e:
        return f"日期计算失败: {str(e)}"


def days_between(date1: str, date2: str) -> str:
    """计算两个日期之间相差的天数"""
    try:
        d1 = datetime.strptime(date1, "%Y-%m-%d")
        d2 = datetime.strptime(date2, "%Y-%m-%d")
        diff = (d2 - d1).days
        return f"{date1} 到 {date2} 相差 {abs(diff)} 天"
    except ValueError:
        return "日期格式错误，请使用 YYYY-MM-DD 格式"
    except Exception as e:
        return f"计算失败: {str(e)}"


def weekday(date_str: str) -> str:
    """查询指定日期是星期几"""
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        return f"{date_str} 是 {weekdays[date.weekday()]}"
    except ValueError:
        return "日期格式错误，请使用 YYYY-MM-DD 格式"
    except Exception as e:
        return f"查询失败: {str(e)}"


tool_defs = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前日期和时间，支持指定时区偏移",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone_offset": {
                        "type": "string",
                        "description": "时区偏移小时数，默认+8（北京时间），例如：+0 表示 UTC，-5 表示美国东部",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_date",
            "description": "日期加减计算，给定日期加上或减去指定天数",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_str": {
                        "type": "string",
                        "description": "日期，格式 YYYY-MM-DD，例如：2026-05-02",
                    },
                    "days": {
                        "type": "integer",
                        "description": "天数，正数表示未来，负数表示过去",
                    },
                },
                "required": ["date_str", "days"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "days_between",
            "description": "计算两个日期之间相差的天数",
            "parameters": {
                "type": "object",
                "properties": {
                    "date1": {
                        "type": "string",
                        "description": "第一个日期，格式 YYYY-MM-DD",
                    },
                    "date2": {
                        "type": "string",
                        "description": "第二个日期，格式 YYYY-MM-DD",
                    },
                },
                "required": ["date1", "date2"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "weekday",
            "description": "查询指定日期是星期几",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_str": {
                        "type": "string",
                        "description": "日期，格式 YYYY-MM-DD",
                    },
                },
                "required": ["date_str"],
            },
        },
    },
]
