from app.database import SessionLocal
from app.models import Chapter, StoryMemory
from app.services.llm_service import LLMService
from app.utils import render_prompt, safe_parse_json

class MemoryService:
    def __init__(self, db=None):
        self.db = db or SessionLocal()
        self.llm = LLMService()

    def extract_memory(self, chapter_id: int):
        chapter = self.db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            return

        prompt = render_prompt("memory_extract.md", {
            "chapter_text": chapter.final_text or chapter.draft_text or ""
        })

        result = self.llm.generate(prompt, provider="checker")
        parsed = safe_parse_json(result)

        if not parsed:
            parsed = {
                "chapter_summary": (chapter.final_text or "")[:300],
                "character_changes": [],
                "relationship_changes": [],
                "new_foreshadowing": [],
                "resolved_foreshadowing": [],
                "world_rules": [],
                "important_items": [],
                "important_dialogues": [],
                "next_hints": []
            }

        chapter.summary = parsed.get("chapter_summary", "")
        self.db.commit()

        memory_types = [
            ("character_changes", "character_change"),
            ("relationship_changes", "relationship_change"),
            ("new_foreshadowing", "foreshadowing"),
            ("resolved_foreshadowing", "resolved_foreshadowing"),
            ("world_rules", "world_rule"),
            ("important_items", "important_item"),
            ("important_dialogues", "important_dialogue"),
            ("next_hints", "next_hint")
        ]

        for key, mtype in memory_types:
            for item in parsed.get(key, []):
                mem = StoryMemory(
                    novel_id=chapter.novel_id,
                    chapter_id=chapter_id,
                    memory_type=mtype,
                    content=item,
                    importance=5
                )
                self.db.add(mem)
        self.db.commit()