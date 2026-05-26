from app.database import SessionLocal
from app.models import Novel, NovelBible, TaskLog
from app.services.llm_service import LLMService
from app.utils import render_prompt
from datetime import datetime

class BibleService:
    def __init__(self):
        self.llm = LLMService()
        self.db = SessionLocal()

    def generate_bible(self, novel_id: int) -> NovelBible:
        novel = self.db.query(Novel).filter(Novel.id == novel_id).first()
        if not novel:
            raise ValueError("Novel not found")

        # 检查是否已存在
        existing = self.db.query(NovelBible).filter(NovelBible.novel_id == novel_id).first()
        if existing:
            return existing

        # 渲染提示词
        prompt = render_prompt("novel_bible.md", {
            "title": novel.title,
            "genre": novel.genre,
            "style": novel.style,
            "description": novel.description or "",
            "target_words": novel.target_words,
            "chapter_words": novel.chapter_words,
        })

        # 调用 LLM
        full_text = self.llm.generate(prompt, provider="main")

        # 创建 Bible
        bible = NovelBible(
            novel_id=novel_id,
            full_text=full_text,
            forbidden_rules="所有角色均为成年人，所有亲密互动自愿。"
        )
        self.db.add(bible)
        self.db.commit()
        self.db.refresh(bible)

        # 记录日志
        log = TaskLog(
            novel_id=novel_id,
            task_type="generate_bible",
            status="success",
            message=f"Novel bible generated for {novel.title}"
        )
        self.db.add(log)
        self.db.commit()

        return bible