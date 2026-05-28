import os
from app.database import SessionLocal
from app.models import Chapter, Novel
from app.config import settings

class ExportService:
    def __init__(self, db=None):
        self.db = db or SessionLocal()
        export_cfg = getattr(settings, "export", {})
        self.export_dir = export_cfg.get("export_dir", "data/exports")
        os.makedirs(self.export_dir, exist_ok=True)

    def export_chapter(self, chapter_id: int):
        chapter = self.db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            return

        novel = chapter.novel
        novel_dir = os.path.join(self.export_dir, novel.title.replace(" ", "_"))
        os.makedirs(novel_dir, exist_ok=True)

        md_path = os.path.join(novel_dir, f"chapter_{chapter.chapter_no:04d}.md")
        txt_path = os.path.join(novel_dir, f"chapter_{chapter.chapter_no:04d}.txt")

        md_content = f"# 第 {chapter.chapter_no} 章 {chapter.title or ''}\n\n{chapter.final_text or chapter.draft_text or ''}"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        txt_content = f"第 {chapter.chapter_no} 章 {chapter.title or ''}\n\n{chapter.final_text or chapter.draft_text or ''}"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(txt_content)
        return md_path

    def export_full_novel(self, novel_id: int, format: str = "markdown"):
        novel = self.db.query(Novel).filter(Novel.id == novel_id).first()
        if not novel:
            return ""

        chapters = self.db.query(Chapter).filter(Chapter.novel_id == novel_id).order_by(Chapter.chapter_no).all()
        novel_dir = os.path.join(self.export_dir, novel.title.replace(" ", "_"))
        os.makedirs(novel_dir, exist_ok=True)

        full_content = ""
        for ch in chapters:
            text = ch.final_text or ch.draft_text or ""
            if format == "markdown":
                full_content += f"# 第 {ch.chapter_no} 章 {ch.title or ''}\n\n{text}\n\n"
            else:
                full_content += f"第 {ch.chapter_no} 章 {ch.title or ''}\n\n{text}\n\n"

        ext = "md" if format == "markdown" else "txt"
        path = os.path.join(novel_dir, f"{novel.title.replace(' ', '_')}_full.{ext}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(full_content)
        return path
