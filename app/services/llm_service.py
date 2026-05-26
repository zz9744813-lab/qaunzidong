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
            raise ValueError(f"Missing API configuration for provider: {provider}")

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
                response.raise_for_status()
                data = response.json()
                
                if "choices" in data and len(data["choices"]) > 0:
                    content = data["choices"][0]["message"]["content"]
                    return content.strip()
                else:
                    logger.warning(f"Empty response from {provider}")
                    return ""
                    
            except Exception as e:
                logger.error(f"LLM call failed (attempt {attempt + 1}/{self.retry_times}): {str(e)}")
                if attempt < self.retry_times - 1:
                    time.sleep(self.retry_interval)
                else:
                    raise Exception(f"LLM call failed after {self.retry_times} attempts: {str(e)}")
        
        return ""