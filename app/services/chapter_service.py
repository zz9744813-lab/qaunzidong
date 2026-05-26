from app.database import SessionLocal
from app.models import Novel, Chapter, NovelBible, StoryMemory, TaskLog
from app.services.llm_service import LLMService
from app.services.quality_service import QualityService
from app.services.memory_service import MemoryService
from app.services.export_service import ExportService
from app.utils import render_prompt
from app.config import settings

class ChapterService:
    def __init__(self, db=None):
        self.db = db or SessionLocal()
        self.llm = LLMService()
        self.quality = QualityService(self.db)
        self.memory = MemoryService(self.db)
        self.export = ExportService(self.db)

    def generate_next_chapter(self, novel_id: int) -> Chapter:
        novel = self.db.query(Novel).filter(Novel.id == novel_id).first()
        if not novel:
            raise ValueError("Novel not found")

        # 获取 Bible
        bible = self.db.query(NovelBible).filter(NovelBible.novel_id == novel_id).first()
        if not bible:
            from app.services.bible_service import BibleService
            bible_service = BibleService(self.db)
            bible = bible_service.generate_bible(novel_id)

        # 确定章节号
        last_chapter = self.db.query(Chapter).filter(Chapter.novel_id == novel_id).order_by(Chapter.chapter_no.desc()).first()
        chapter_no = (last_chapter.chapter_no + 1) if last_chapter else 1

        # 获取最近摘要
        recent_memories = self.db.query(StoryMemory).filter(
            StoryMemory.novel_id == novel_id
        ).order_by(StoryMemory.created_at.desc()).limit(5).all()
        recent_summaries = "\n".join([m.content for m in recent_memories])

        # 1. 生成细纲
        outline_prompt = render_prompt("chapter_outline.md", {
            "novel_bible": bible.full_text,
            "recent_summaries": recent_summaries,
            "chapter_no": chapter_no,
            "style": novel.style,
            "chapter_words": novel.chapter_words,
        })
        outline = self.llm.generate(outline_prompt, provider="main")

        # 创建章节
        chapter = Chapter(
            novel_id=novel_id,
            chapter_no=chapter_no,
            outline=outline,
            status="outline_done"
        )
        self.db.add(chapter)
        self.db.commit()
        self.db.refresh(chapter)

        # 2. 生成正文
        write_prompt = render_prompt("chapter_write.md", {
            "novel_bible": bible.full_text,
            "recent_summaries": recent_summaries,
            "chapter_outline": outline,
            "style": novel.style,
            "chapter_words": novel.chapter_words,
        })
        draft_text = self.llm.generate(write_prompt, provider="main")
        chapter.draft_text = draft_text
        chapter.status = "draft_done"
        self.db.commit()

        # 3. 质检 + 重写
        best_text = draft_text
        best_score = 0
        max_rewrite = settings.writing["max_rewrite_times"]
        min_score = settings.writing["min_quality_score"]

        for i in range(max_rewrite + 1):
            review = self.quality.review_chapter(chapter.id, text=best_text)
            if review.get("score", 0) > best_score:
                best_score = review.get("score", 0)
                chapter.final_text = best_text
                chapter.quality_score = best_score
                self.db.commit()

            if review.get("score", 0) >= min_score:
                break

            if i < max_rewrite:
                best_text = self.quality.rewrite_chapter(chapter.id, review)

        # 4. 润色
        if settings.writing["auto_polish"]:
            polished = self.quality.polish_chapter(chapter.id)
            chapter.final_text = polished
            chapter.status = "polished"

        chapter.word_count = len("".join(chapter.final_text.split()))
        chapter.status = "final"
        self.db.commit()

        # 5. 提取记忆
        self.memory.extract_memory(chapter.id)

        # 6. 导出
        self.export.export_chapter(chapter.id)

        # 更新小说进度
        novel.current_chapter_no = chapter_no
        novel.total_words = (novel.total_words or 0) + chapter.word_count
        novel.failed_times = 0
        self.db.commit()

        # 日志
        log = TaskLog(
            novel_id=novel_id,
            chapter_id=chapter.id,
            task_type="generate_chapter",
            status="success",
            message=f"Chapter {chapter_no} generated"
        )
        self.db.add(log)
        self.db.commit()

        return chapter