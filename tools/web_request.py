import requests
import json as json_mod
import socket
import ipaddress
from urllib.parse import urlparse


def _validate_url(url: str) -> None:
    """防御 SSRF: 拒绝私有/内网/回环地址"""
    parsed = urlparse(url)
    if parsed.hostname is None:
        raise PermissionError(f"无法解析 URL 主机名: {url}")
    try:
        ip = socket.gethostbyname(parsed.hostname)
    except socket.gaierror:
        raise PermissionError(f"DNS 解析失败: {parsed.hostname}")
    addr = ipaddress.ip_address(ip)
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast:
        raise PermissionError(f"禁止访问内网地址: {ip}")
    if ip == "0.0.0.0":
        raise PermissionError(f"禁止访问无效地址: {ip}")


def http_get(url: str, headers: str = "{}") -> str:
    """发送 HTTP GET 请求"""
    try:
        _validate_url(url)
        parsed_headers = json_mod.loads(headers) if headers else {}
        resp = requests.get(url, headers=parsed_headers, timeout=10)
        content_type = resp.headers.get("content-type", "")
        result = f"状态码: {resp.status_code}\n"

        if "application/json" in content_type:
            body = json_mod.dumps(resp.json(), ensure_ascii=False, indent=2)
            result += f"响应 (JSON):\n{body[:3000]}"
        else:
            result += f"响应:\n{resp.text[:3000]}"

        if len(resp.text) > 3000:
            result += "\n...[内容已截断]"
        return result
    except requests.Timeout:
        return "请求超时"
    except Exception as e:
        return f"HTTP GET 失败: {str(e)}"


def http_post(url: str, body: str = "{}", headers: str = '{"Content-Type": "application/json"}') -> str:
    """发送 HTTP POST 请求"""
    try:
        _validate_url(url)
        parsed_headers = json_mod.loads(headers) if headers else {}
        resp = requests.post(url, data=body, headers=parsed_headers, timeout=10)
        content_type = resp.headers.get("content-type", "")
        result = f"状态码: {resp.status_code}\n"

        if "application/json" in content_type:
            response_body = json_mod.dumps(resp.json(), ensure_ascii=False, indent=2)
            result += f"响应 (JSON):\n{response_body[:3000]}"
        else:
            result += f"响应:\n{resp.text[:3000]}"

        if len(resp.text) > 3000:
            result += "\n...[内容已截断]"
        return result
    except requests.Timeout:
        return "请求超时"
    except Exception as e:
        return f"HTTP POST 失败: {str(e)}"


tool_defs = [
    {
        "type": "function",
        "function": {
            "name": "http_get",
            "description": "发送 HTTP GET 请求并获取响应内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "请求的 URL 地址",
                    },
                    "headers": {
                        "type": "string",
                        "description": "请求头，JSON 字符串格式，例如：'{\"Authorization\": \"Bearer xxx\"}'",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "http_post",
            "description": "发送 HTTP POST 请求并获取响应内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "请求的 URL 地址",
                    },
                    "body": {
                        "type": "string",
                        "description": "请求体内容",
                    },
                    "headers": {
                        "type": "string",
                        "description": "请求头，JSON 字符串格式",
                    },
                },
                "required": ["url"],
            },
        },
    },
]
