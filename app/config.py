import os
from dotenv import load_dotenv
import yaml
import re

load_dotenv()

def _substitute_env_vars(value):
    """递归替换 ${VAR} 格式的环境变量，缺失时直接 raise"""
    if isinstance(value, str):
        def replace_var(match):
            var_name = match.group(1)
            env_value = os.getenv(var_name)
            if env_value is None:
                raise ValueError(f"Missing required environment variable: {var_name}")
            return env_value
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

        # 默认值
        defaults = {
            "database": {"url": "sqlite:///data/novel_factory.db"},
            "writing": {
                "default_chapter_words": 3500,
                "recent_summary_count": 5,
                "min_quality_score": 80,
                "max_rewrite_times": 2,
                "auto_polish": True,
                "auto_memory_extract": True,
            },
            "scheduler": {
                "enabled": True,
                "interval_minutes": 10,
                "max_chapters_per_day": 10,
                "max_failed_times": 5,
            },
            "export": {
                "export_dir": "data/exports",
                "enable_markdown": True,
                "enable_txt": True,
            },
            "log": {
                "log_dir": "data/logs",
                "log_file": "data/logs/app.log",
            },
        }

        config_path = "config.yaml"
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                yaml_config = yaml.safe_load(f) or {}

            # 递归替换环境变量
            yaml_config = _substitute_env_vars(yaml_config)

            # 合并配置
            self.database_url = yaml_config.get("database", {}).get("url", defaults["database"]["url"])
            self.llm = yaml_config.get("llm", {})
            self.writing = {**defaults["writing"], **yaml_config.get("writing", {})}
            self.scheduler = {**defaults["scheduler"], **yaml_config.get("scheduler", {})}
            self.export = {**defaults["export"], **yaml_config.get("export", {})}
            self.log = {**defaults["log"], **yaml_config.get("log", {})}
        else:
            # 无 config.yaml 时使用默认
            self.database_url = defaults["database"]["url"]
            self.llm = {}
            self.writing = defaults["writing"]
            self.scheduler = defaults["scheduler"]
            self.export = defaults["export"]
            self.log = defaults["log"]


settings = Settings()