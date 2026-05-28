import os
import time
import json
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

    @staticmethod
    def _normalize_max_tokens(value, default: int = 8000) -> int:
        try:
            tokens = int(value or default)
        except (TypeError, ValueError):
            tokens = default
        return max(1, min(tokens, 65536))

    @staticmethod
    def _normalize_timeout(value, default: int = 900) -> int:
        try:
            timeout = int(value or default)
        except (TypeError, ValueError):
            timeout = default
        return max(30, min(timeout, 1800))

    @staticmethod
    def _normalize_retry_times(value, default: int = 2) -> int:
        try:
            retries = int(value or default)
        except (TypeError, ValueError):
            retries = default
        return max(1, min(retries, 5))

    @staticmethod
    def _stream_enabled() -> bool:
        value = os.getenv("LLM_STREAM", "true").strip().lower()
        return value not in {"0", "false", "no", "off"}

    @staticmethod
    def _extract_openai_content(data: dict) -> str:
        if "choices" in data and len(data["choices"]) > 0:
            message = data["choices"][0].get("message") or {}
            return (message.get("content") or "").strip()
        return ""

    def _consume_openai_stream(self, response) -> tuple[str, str]:
        parts = []
        raw_lines = []
        # SSE streams from several OpenAI-compatible gateways omit charset.
        # requests may then decode UTF-8 Chinese as latin-1 if decode_unicode=True.
        # Always decode the raw bytes ourselves.
        for raw_line in response.iter_lines(decode_unicode=False):
            if not raw_line:
                continue
            if isinstance(raw_line, bytes):
                line = raw_line.decode("utf-8", errors="replace")
            else:
                line = str(raw_line)
            raw_lines.append(line)
            if line.startswith("data:"):
                line = line[5:].strip()
            if line == "[DONE]":
                break
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "error" in event:
                raise RuntimeError(str(event["error"]))
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                parts.append(content)
        return "".join(parts).strip(), "\n".join(raw_lines)[-4000:]

    def _post_openai(self, url: str, headers: dict, payload: dict, timeout: int, stream: bool):
        if stream:
            stream_payload = dict(payload)
            stream_payload["stream"] = True
            response = requests.post(
                url,
                json=stream_payload,
                headers=headers,
                timeout=(30, timeout),
                stream=True
            )
            if response.status_code != 200:
                response.raise_for_status()
            content, raw = self._consume_openai_stream(response)
            return content, raw

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=(30, timeout)
        )
        if response.status_code != 200:
            response.raise_for_status()
        raw = response.text[:4000] if response.text else None
        data = response.json()
        return self._extract_openai_content(data), raw

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
                    "max_tokens": self._normalize_max_tokens(provider.max_tokens),
                    "timeout_seconds": provider.timeout_seconds or 180,
                    "retry_times": provider.retry_times or 3,
                    "name": provider.name
                }
            if role != "main":
                fallback = self.db.query(LLMProvider).filter(
                    LLMProvider.role == "main",
                    LLMProvider.enabled == 1
                ).first()
                if fallback:
                    from app.utils import decrypt_api_key
                    logger.warning(f"Provider role {role} not configured, falling back to main")
                    return {
                        "base_url": fallback.base_url,
                        "api_key": decrypt_api_key(fallback.api_key_encrypted),
                        "model": fallback.model,
                        "temperature": float(fallback.temperature or 0.85),
                        "max_tokens": self._normalize_max_tokens(fallback.max_tokens),
                        "timeout_seconds": fallback.timeout_seconds or 180,
                        "retry_times": fallback.retry_times or 3,
                        "name": fallback.name
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
                "max_tokens": self._normalize_max_tokens(config.get("max_tokens", 8000)),
                "timeout_seconds": config.get("timeout_seconds", 180),
                "retry_times": config.get("retry_times", 3),
            }
        if role != "main" and "main" in providers:
            config = providers["main"]
            logger.warning(f"Provider role {role} not configured in config, falling back to main")
            return {
                "base_url": config.get("base_url") or os.getenv("MAIN_BASE_URL"),
                "api_key": config.get("api_key") or os.getenv("MAIN_API_KEY"),
                "model": config.get("model") or os.getenv("MAIN_MODEL"),
                "temperature": config.get("temperature", 0.85),
                "max_tokens": self._normalize_max_tokens(config.get("max_tokens", 8000)),
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
            "max_tokens": self._normalize_max_tokens(max_tokens or config.get("max_tokens", 8000))
        }

        timeout = self._normalize_timeout(config.get("timeout_seconds", 900), 900)
        retry_times = self._normalize_retry_times(config.get("retry_times", 2), 2)
        stream = self._stream_enabled()

        for attempt in range(retry_times):
            try:
                content, _raw = self._post_openai(
                    f"{base_url}/chat/completions",
                    headers,
                    payload,
                    timeout,
                    stream
                )
                if content:
                    return content
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
                "max_tokens": self._normalize_max_tokens(max_tokens or config.get("max_tokens", 8000))
            }
            
            timeout = self._normalize_timeout(config.get("timeout_seconds", 900), 900)
            retry_times = self._normalize_retry_times(config.get("retry_times", 2), 2)
            stream = self._stream_enabled()
            
            for attempt in range(retry_times):
                try:
                    content, raw_response = self._post_openai(
                        f"{base_url}/chat/completions",
                        headers,
                        payload,
                        timeout,
                        stream
                    )
                    result["raw_response"] = raw_response
                    if content:
                        result["content"] = content
                        break
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
