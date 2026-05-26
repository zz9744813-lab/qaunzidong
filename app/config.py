import os
from dotenv import load_dotenv
import yaml

load_dotenv()

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
                return config.get("llm", {})
        return {}

settings = Settings()