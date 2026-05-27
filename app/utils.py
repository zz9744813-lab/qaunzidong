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

# ==================== API Key 加密工具 (P4) ====================
from cryptography.fernet import Fernet
import base64

def _get_fernet():
    """从环境变量或配置获取加密 key"""
    from app.config import settings
    secret = getattr(settings, 'app_secret_key', None) or os.getenv('APP_SECRET_KEY', 'dev-secret-key-change-in-prod')
    # 确保是 32 字节的 base64
    key = secret.encode() if isinstance(secret, str) else secret
    if len(key) < 32:
        key = key.ljust(32, b'0')[:32]
    fernet_key = base64.urlsafe_b64encode(key[:32])
    return Fernet(fernet_key)

def encrypt_api_key(plain_key: str) -> str:
    """加密 API Key"""
    if not plain_key:
        return ""
    f = _get_fernet()
    return f.encrypt(plain_key.encode()).decode()

def decrypt_api_key(encrypted_key: str) -> str:
    """解密 API Key"""
    if not encrypted_key:
        return ""
    try:
        f = _get_fernet()
        return f.decrypt(encrypted_key.encode()).decode()
    except Exception:
        # 如果解密失败，可能是明文（兼容旧数据）
        return encrypted_key

def mask_api_key(key: str) -> str:
    """脱敏显示：sk-****abcd"""
    if not key or len(key) < 8:
        return "********"
    return key[:3] + "****" + key[-4:]
