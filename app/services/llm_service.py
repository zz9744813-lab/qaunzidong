import os
import time
import requests
from typing import Optional
from sqlalchemy.orm import Session
from app.models import LLMProvider
from app.config import settings
from loguru import logger

class LLMService:
    def __init__(self, db: Session = None):
        self.db = db
        self.timeout = 180
        self.retry_times = 3
        self.retry_interval = 5

    def _get_provider_config(self, role: str = "main"):
        """优先从数据库读取，其次从 config.yaml"""
        # 1. 优先从数据库读取
        if self.db:
            provider = self.db.query(LLMProvider).filter(
                LLMProvider.role == role,
                LLMProvider.enabled == 1
            ).first()
            if provider:
                from app.utils import decrypt_api_key
                return {
                    "base_url": provider.base_url,
                    "api_key": decrypt_api_key(provider.api_key_encrypted),
                    "model": provider.model,
                    "temperature": float(provider.temperature or 0.85),
                    "max_tokens": provider.max_tokens or 8000,
                    "timeout_seconds": provider.timeout_seconds or 180,
                    "retry_times": provider.retry_times or 3,
                    "name": provider.name
                }

        # 2. 回退到 config.yaml
        providers = settings.llm.get("providers", {})
        if role in providers:
            config = providers[role]
            return {
                "base_url": config.get("base_url") or os.getenv(f"{role.upper()}_BASE_URL"),
                "api_key": config.get("api_key") or os.getenv(f"{role.upper()}_API_KEY"),
                "model": config.get("model") or os.getenv(f"{role.upper()}_MODEL"),
                "temperature": config.get("temperature", 0.85),
                "max_tokens": config.get("max_tokens", 8000),
                "timeout_seconds": config.get("timeout_seconds", 180),
                "retry_times": config.get("retry_times", 3),
            }

        # 3. 都没有则报错
        raise ValueError(f"未找到角色为 {role} 的模型配置，请先到 /settings/llm 添加")

    def generate(
        self,
        prompt: str,
        provider: str = "main",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        db: Session = None
    ) -> str:
        """调用 LLM 生成内容"""
        if db:
            self.db = db

        config = self._get_provider_config(provider)

        base_url = config["base_url"].rstrip("/")
        api_key = config["api_key"]
        model = config["model"]

        if not base_url or not api_key or not model:
            raise ValueError(f"模型配置不完整: {provider}")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature or config.get("temperature", 0.85),
            "max_tokens": max_tokens or config.get("max_tokens", 8000)
        }

        timeout = config.get("timeout_seconds", 180)
        retry_times = config.get("retry_times", 3)

        for attempt in range(retry_times):
            try:
                response = requests.post(
                    f"{base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=timeout
                )

                if response.status_code != 200:
                    error_text = response.text[:1000] if response.text else "No response body"
                    logger.error(f"LLM API error - Provider: {provider}, Model: {model}, Status: {response.status_code}")
                    response.raise_for_status()

                data = response.json()
                if "choices" in data and len(data["choices"]) > 0:
                    content = data["choices"][0]["message"]["content"]
                    return content.strip()
                else:
                    logger.warning(f"Empty response from {provider}")
                    return ""

            except Exception as e:
                error_msg = f"LLM call failed (attempt {attempt + 1}/{retry_times}) - {str(e)}"
                logger.error(error_msg)
                if attempt < retry_times - 1:
                    time.sleep(self.retry_interval)
                else:
                    raise Exception(error_msg)

        return ""
    def generate_with_trace(self, prompt: str, provider: str = "main", 
                           temperature: Optional[float] = None,
                           max_tokens: Optional[int] = None,
                           db: Session = None) -> dict:
        """带完整追踪信息的 LLM 调用"""
        import time
        start_time = time.time()
        
        result = {
            "content": "",
            "prompt": prompt,
            "model": "",
            "provider_role": provider,
            "elapsed_seconds": 0,
            "error": None,
            "raw_response": None
        }
        
        try:
            if db:
                self.db = db
            
            config = self._get_provider_config(provider)
            result["model"] = config.get("model", "")
            
            base_url = config["base_url"].rstrip("/")
            api_key = config["api_key"]
            model = config["model"]
            
            if not base_url or not api_key or not model:
                raise ValueError(f"模型配置不完整: {provider}")
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature or config.get("temperature", 0.85),
                "max_tokens": max_tokens or config.get("max_tokens", 8000)
            }
            
            timeout = config.get("timeout_seconds", 180)
            retry_times = config.get("retry_times", 3)
            
            for attempt in range(retry_times):
                try:
                    response = requests.post(
                        f"{base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                        timeout=timeout
                    )
                    
                    result["raw_response"] = response.text[:2000] if response.text else None
                    
                    if response.status_code != 200:
                        error_text = response.text[:500] if response.text else "No response body"
                        logger.error(f"LLM API error - Provider: {provider}, Model: {model}, Status: {response.status_code}")
                        response.raise_for_status()
                    
                    data = response.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        content = data["choices"][0]["message"]["content"]
                        result["content"] = content.strip()
                        break
                    else:
                        logger.warning(f"Empty response from {provider}")
                        result["content"] = ""
                        break
                        
                except Exception as e:
                    error_msg = f"LLM call failed (attempt {attempt + 1}/{retry_times}) - {str(e)}"
                    logger.error(error_msg)
                    if attempt < retry_times - 1:
                        time.sleep(self.retry_interval)
                    else:
                        result["error"] = error_msg
                        raise Exception(error_msg)
            
            result["elapsed_seconds"] = round(time.time() - start_time, 2)
            return result
            
        except Exception as e:
            result["error"] = str(e)
            result["elapsed_seconds"] = round(time.time() - start_time, 2)
            raise

