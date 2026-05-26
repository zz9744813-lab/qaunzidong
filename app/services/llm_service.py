import os
import time
import requests
from typing import Optional
from app.config import settings
from loguru import logger

class LLMService:
    def __init__(self):
        self.providers = settings.llm.get("providers", {})
        self.timeout = settings.llm.get("timeout_seconds", 180)
        self.retry_times = settings.llm.get("retry_times", 3)
        self.retry_interval = settings.llm.get("retry_interval_seconds", 5)

    def generate(
        self,
        prompt: str,
        provider: str = "main",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """调用 LLM 生成内容"""
        if provider not in self.providers:
            provider = "main"
        
        config = self.providers.get(provider, {})
        base_url = config.get("base_url", os.getenv(f"{provider.upper()}_BASE_URL"))
        api_key = config.get("api_key", os.getenv(f"{provider.upper()}_API_KEY"))
        model = config.get("model", os.getenv(f"{provider.upper()}_MODEL"))
        
        if not base_url or not api_key or not model:
            error_msg = f"Missing API configuration for provider: {provider}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # 清理 base_url 末尾的斜杠
        base_url = base_url.rstrip("/")

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

        for attempt in range(self.retry_times):
            try:
                response = requests.post(
                    f"{base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout
                )
                
                if response.status_code != 200:
                    error_text = response.text[:1000] if response.text else "No response body"
                    logger.error(f"LLM API error - Provider: {provider}, Model: {model}, Status: {response.status_code}, Response: {error_text}")
                    response.raise_for_status()
                
                data = response.json()
                
                if "choices" in data and len(data["choices"]) > 0:
                    content = data["choices"][0]["message"]["content"]
                    return content.strip()
                else:
                    logger.warning(f"Empty response from {provider} - {model}")
                    return ""
                    
            except Exception as e:
                error_msg = f"LLM call failed (attempt {attempt + 1}/{self.retry_times}) - Provider: {provider}, Model: {model}, Error: {str(e)}"
                logger.error(error_msg)
                if attempt < self.retry_times - 1:
                    time.sleep(self.retry_interval)
                else:
                    raise Exception(error_msg)
        
        return ""