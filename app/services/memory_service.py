from app.database import SessionLocal
from app.models import Chapter, StoryMemory
from app.services.llm_service import LLMService
from app.utils import render_prompt, safe_parse_json

class MemoryService:
    def __init__(self, db=None):
        self.db = db or SessionLocal()
        self.llm = LLMService(self.db)

    def record_memory(
        self,
        novel_id: int,
        content: str,
        memory_type: str,
        chapter_id: int = None,
        entity_name: str = None,
        importance: int = 5,
        tags: str = None,
        is_resolved: int = 0,
    ):
        if not content:
            return None
        mem = StoryMemory(
            novel_id=novel_id,
            chapter_id=chapter_id,
            memory_type=memory_type,
            entity_name=entity_name,
            content=content,
            importance=importance,
            tags=tags,
            is_resolved=is_resolved,
        )
        self.db.add(mem)
        self.db.commit()
        self.db.refresh(mem)
        return mem

    def build_context(self, novel_id: int, limit: int = 20) -> str:
        memories = self.db.query(StoryMemory).filter(
            StoryMemory.novel_id == novel_id,
            StoryMemory.is_resolved == 0
        ).order_by(StoryMemory.importance.desc(), StoryMemory.created_at.desc()).limit(limit).all()
        if not memories:
            return "暂无长期记忆。"
        lines = []
        for mem in memories:
            entity = f"{mem.entity_name}: " if mem.entity_name else ""
            lines.append(f"- [{mem.memory_type}] {entity}{mem.content}")
        return "\n".join(lines)

    def extract_memory(self, chapter_id: int):
        chapter = self.db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            return

        prompt = render_prompt("memory_extract.md", {
            "chapter_text": chapter.final_text or chapter.draft_text or "",
            "existing_memory": self.build_context(chapter.novel_id, limit=18)[:4500],
        })

        result = self.llm.generate(prompt, provider="checker", max_tokens=1800)
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
                "next_hints": [],
                "pov_state": [],
                "character_goals": []
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
            ("next_hints", "next_hint"),
            ("pov_state", "pov_state"),
            ("character_goals", "character_goal")
        ]

        for key, mtype in memory_types:
            for item in parsed.get(key, []):
                self.record_memory(
                    novel_id=chapter.novel_id,
                    chapter_id=chapter_id,
                    memory_type=mtype,
                    content=item,
                    importance=7 if mtype in ["foreshadowing", "world_rule", "pov_state"] else 5,
                )

        return parsed

    def get_important_memories(self, novel_id: int, limit: int = 10):
        """获取重要的长期记忆（未解决 + 高重要性）"""
        memories = self.db.query(StoryMemory).filter(
            StoryMemory.novel_id == novel_id,
            StoryMemory.is_resolved == 0
        ).order_by(StoryMemory.importance.desc()).limit(limit).all()
        return memories
