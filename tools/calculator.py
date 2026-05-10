def calculate(expression: str) -> str:
    """安全地计算数学表达式"""
    expr = expression.replace(" ", "")
    allowed = set("0123456789+-*/%().")
    if not all(c in allowed for c in expr):
        return "错误：表达式包含非法字符"
    try:
        result = eval(expr)
        return f"{expression} = {result}"
    except ZeroDivisionError:
        return "错误：除数不能为0"
    except Exception as e:
        return f"计算错误: {str(e)}"


tool_def = {
    "type": "function",
    "function": {
        "name": "calculate",
        "description": "执行数学计算，支持加减乘除和括号",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式，例如：1+2*3 或 (10-5)/2",
                }
            },
            "required": ["expression"],
        },
    },
}
