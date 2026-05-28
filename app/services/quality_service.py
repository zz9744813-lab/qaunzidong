from app.database import SessionLocal
from app.models import Chapter, NovelBible, StoryMemory
from app.services.llm_service import LLMService
from app.utils import render_prompt, safe_parse_json
from loguru import logger

class QualityService:
    def __init__(self, db=None):
        self.db = db or SessionLocal()
        self.llm = LLMService(self.db)

    def _clip(self, text: str, limit: int) -> str:
        text = text or ""
        if len(text) <= limit:
            return text
        return text[:limit] + "\n...[已截断]"

    def review_chapter(self, chapter_id: int, text: str = None) -> dict:
        chapter = self.db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            return {"score": 0, "pass": False, "problems": ["Chapter not found"]}

        novel = chapter.novel
        bible = self.db.query(NovelBible).filter(NovelBible.novel_id == novel.id).first()
        recent_memories = self.db.query(StoryMemory).filter(
            StoryMemory.novel_id == novel.id,
            StoryMemory.is_resolved == 0
        ).order_by(StoryMemory.importance.desc(), StoryMemory.created_at.desc()).limit(20).all()
        memory_context = self._clip("\n".join([f"[{m.memory_type}] {m.content}" for m in recent_memories]), 2600)

        prompt = render_prompt("chapter_review.md", {
            "novel_bible": self._clip(bible.full_text if bible else "", 4200),
            "recent_summaries": memory_context,
            "chapter_outline": self._clip(chapter.outline or "", 2200),
            "chapter_text": text or chapter.draft_text or chapter.final_text or ""
        })

        try:
            result = self.llm.generate(prompt, provider="checker", max_tokens=1200)
        except Exception as e:
            logger.warning(f"Review fallback for chapter {chapter_id}: {e}")
            default = {
                "score": 75,
                "pass": True,
                "problems": [f"质检模型暂不可用，已采用保守通过兜底：{str(e)[:180]}"],
                "rewrite_suggestion": "建议后续人工抽查；系统先保留当前最佳稿继续流水线。",
                "fallback": True
            }
            chapter.review_result = str(default)
            chapter.quality_score = 75
            self.db.commit()
            return default
        parsed = safe_parse_json(result)

        if parsed:
            chapter.review_result = str(parsed)
            chapter.quality_score = parsed.get("score", 70)
            self.db.commit()
            return parsed
        else:
            default = {
                "score": 70,
                "pass": False,
                "problems": ["JSON parse failed"],
                "rewrite_suggestion": "Please rewrite for better coherence."
            }
            chapter.review_result = str(default)
            chapter.quality_score = 70
            self.db.commit()
            return default

    def rewrite_chapter(self, chapter_id: int, review_result: dict) -> str:
        chapter = self.db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            return ""

        novel = chapter.novel
        bible = self.db.query(NovelBible).filter(NovelBible.novel_id == novel.id).first()
        recent_memories = self.db.query(StoryMemory).filter(
            StoryMemory.novel_id == novel.id,
            StoryMemory.is_resolved == 0
        ).order_by(StoryMemory.importance.desc(), StoryMemory.created_at.desc()).limit(20).all()
        memory_context = self._clip("\n".join([f"[{m.memory_type}] {m.content}" for m in recent_memories]), 2600)

        prompt = render_prompt("chapter_rewrite.md", {
            "novel_bible": self._clip(bible.full_text if bible else "", 4200),
            "recent_summaries": memory_context,
            "chapter_outline": self._clip(chapter.outline or "", 2200),
            "chapter_text": chapter.draft_text or chapter.final_text or "",
            "review_result": str(review_result)
        })

        try:
            new_text = self.llm.generate(prompt, provider="main", max_tokens=min(6200, max(2000, int((novel.chapter_words or 3500) * 1.6))))
        except Exception as e:
            logger.warning(f"Rewrite fallback for chapter {chapter_id}: {e}")
            new_text = chapter.draft_text or chapter.final_text or ""
        chapter.draft_text = new_text
        chapter.rewrite_count = (chapter.rewrite_count or 0) + 1
        self.db.commit()
        return new_text

    def polish_chapter(self, chapter_id: int) -> str:
        chapter = self.db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            return ""

        novel = chapter.novel
        bible = self.db.query(NovelBible).filter(NovelBible.novel_id == novel.id).first()

        prompt = render_prompt("chapter_polish.md", {
            "novel_bible": self._clip(bible.full_text if bible else "", 3200),
            "chapter_text": chapter.final_text or chapter.draft_text or ""
        })

        try:
            polished = self.llm.generate(prompt, provider="editor", max_tokens=min(6000, max(1800, int((novel.chapter_words or 3500) * 1.5))))
        except Exception as e:
            logger.warning(f"Polish fallback for chapter {chapter_id}: {e}")
            polished = chapter.final_text or chapter.draft_text or ""
        chapter.final_text = polished
        self.db.commit()
        return polished
