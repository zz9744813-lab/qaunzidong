from app.database import SessionLocal
from app.models import Chapter, NovelBible
from app.services.llm_service import LLMService
from app.utils import render_prompt, safe_parse_json

class QualityService:
    def __init__(self, db=None):
        self.db = db or SessionLocal()
        self.llm = LLMService()

    def review_chapter(self, chapter_id: int, text: str = None) -> dict:
        chapter = self.db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            return {"score": 0, "pass": False, "problems": ["Chapter not found"]}

        novel = chapter.novel
        bible = self.db.query(NovelBible).filter(NovelBible.novel_id == novel.id).first()

        prompt = render_prompt("chapter_review.md", {
            "novel_bible": bible.full_text if bible else "",
            "recent_summaries": "",
            "chapter_outline": chapter.outline or "",
            "chapter_text": text or chapter.draft_text or chapter.final_text or ""
        })

        result = self.llm.generate(prompt, provider="checker")
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

        prompt = render_prompt("chapter_rewrite.md", {
            "novel_bible": bible.full_text if bible else "",
            "recent_summaries": "",
            "chapter_outline": chapter.outline or "",
            "chapter_text": chapter.draft_text or chapter.final_text or "",
            "review_result": str(review_result)
        })

        new_text = self.llm.generate(prompt, provider="main")
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
            "novel_bible": bible.full_text if bible else "",
            "chapter_text": chapter.final_text or chapter.draft_text or ""
        })

        polished = self.llm.generate(prompt, provider="editor")
        chapter.final_text = polished
        self.db.commit()
        return polished