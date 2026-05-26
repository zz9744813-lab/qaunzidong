import re
import json
from typing import Optional, Dict, Any

def count_words(text: str) -> int:
    """中文小说字数统计"""
    return len("".join(text.split()))

def safe_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """安全解析 JSON，处理模型返回的各种格式"""
    if not text or not isinstance(text, str):
        return None
    
    text = text.strip()
    
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # 去除 markdown code block
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    
    text = text.strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # 尝试截取第一个 { 到最后一个 }
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    
    # 尝试找 JSON 数组
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    
    return None

def render_prompt(template_name: str, data: dict) -> str:
    """渲染 Jinja2 提示词模板"""
    from jinja2 import Environment, FileSystemLoader
    import os
    
    template_path = os.path.join("app/prompts", template_name)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Prompt template not found: {template_name}")
    
    env = Environment(loader=FileSystemLoader("app/prompts"))
    template = env.get_template(template_name)
    return template.render(**data)