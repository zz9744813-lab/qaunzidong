import os
from dotenv import load_dotenv
import yaml
import re

load_dotenv()

def _substitute_env_vars(value):
    """递归替换 ${VAR} 格式的环境变量"""
    if isinstance(value, str):
        def replace_var(match):
            var_name = match.group(1)
            return os.getenv(var_name, match.group(0))
        return re.sub(r'\$\{([^}]+)\}', replace_var, value)
    elif isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]
    return value

class Settings:
    def __init__(self):
        self.app_name = "Novel Auto Factory"
        self.debug = True
        
        # Database
        self.database_url = "sqlite:///data/novel_factory.db"
        
        # LLM settings from config.yaml or env
        self.llm = self._load_llm_config()
        
        # Writing settings
        self.writing = {
            "default_chapter_words": 3500,
            "recent_summary_count": 5,
            "min_quality_score": 80,
            "max_rewrite_times": 2,
            "auto_polish": True,
            "auto_memory_extract": True,
        }
        
        # Scheduler
        self.scheduler = {
            "enabled": True,
            "interval_minutes": 10,
            "max_chapters_per_day": 10,
            "max_failed_times": 5,
        }
        
        # Export
        self.export = {
            "export_dir": "data/exports",
            "enable_markdown": True,
            "enable_txt": True,
        }
        
        # Log
        self.log = {
            "log_dir": "data/logs",
            "log_file": "data/logs/app.log",
        }

    def _load_llm_config(self):
        config_path = "config.yaml"
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                llm_config = config.get("llm", {})
                # 递归替换环境变量
                return _substitute_env_vars(llm_config)
        return {}

settings = Settings()