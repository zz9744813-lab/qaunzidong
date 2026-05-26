from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Novel(Base):
    __tablename__ = "novels"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    genre = Column(String)
    style = Column(Text)
    description = Column(Text)
    target_words = Column(Integer, default=1000000)
    chapter_words = Column(Integer, default=3500)
    status = Column(String, default="draft")
    current_chapter_no = Column(Integer, default=0)
    total_words = Column(Integer, default=0)
    failed_times = Column(Integer, default=0)
    generation_lock = Column(Integer, default=0)  # 0 = unlocked, 1 = locked
    locked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    bibles = relationship("NovelBible", back_populates="novel")
    chapters = relationship("Chapter", back_populates="novel")
    memories = relationship("StoryMemory", back_populates="novel")
    logs = relationship("TaskLog", back_populates="novel")

class NovelBible(Base):
    __tablename__ = "novel_bibles"

    id = Column(Integer, primary_key=True, index=True)
    novel_id = Column(Integer, ForeignKey("novels.id"))
    core_selling_point = Column(Text)
    world_setting = Column(Text)
    main_plot = Column(Text)
    character_setting = Column(Text)
    power_system = Column(Text)
    relationship_setting = Column(Text)
    style_guide = Column(Text)
    forbidden_rules = Column(Text)
    full_text = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    novel = relationship("Novel", back_populates="bibles")

class Chapter(Base):
    __tablename__ = "chapters"

    id = Column(Integer, primary_key=True, index=True)
    novel_id = Column(Integer, ForeignKey("novels.id"))
    chapter_no = Column(Integer)
    title = Column(String)
    outline = Column(Text)
    draft_text = Column(Text)
    review_result = Column(Text)
    final_text = Column(Text)
    summary = Column(Text)
    quality_score = Column(Integer, default=0)
    rewrite_count = Column(Integer, default=0)
    word_count = Column(Integer, default=0)
    status = Column(String, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    novel = relationship("Novel", back_populates="chapters")

    __table_args__ = (
        UniqueConstraint("novel_id", "chapter_no", name="uq_novel_chapter_no"),
    )

class StoryMemory(Base):
    __tablename__ = "story_memories"

    id = Column(Integer, primary_key=True, index=True)
    novel_id = Column(Integer, ForeignKey("novels.id"))
    chapter_id = Column(Integer, ForeignKey("chapters.id"), nullable=True)
    memory_type = Column(String)
    entity_name = Column(String, nullable=True)
    content = Column(Text)
    importance = Column(Integer, default=5)
    is_resolved = Column(Integer, default=0)
    tags = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    novel = relationship("Novel", back_populates="memories")

class TaskLog(Base):
    __tablename__ = "task_logs"

    id = Column(Integer, primary_key=True, index=True)
    novel_id = Column(Integer, ForeignKey("novels.id"), nullable=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id"), nullable=True)
    task_type = Column(String)
    status = Column(String)
    message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    novel = relationship("Novel", back_populates="logs")

class AppSetting(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())