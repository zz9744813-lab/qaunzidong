from sqlalchemy.orm import Session
from app.services.task_service import TaskService
from app.services.llm_service import LLMService
from app.services.bible_service import BibleService
from app.services.chapter_service import ChapterService
from app.models import GenerationTask
import time

class AgentRunner:
    def __init__(self, db: Session):
        self.db = db
        self.task_service = TaskService(db)
        self.llm = LLMService(db)

    def run_generate_bible(self, task_id: int):
        """执行生成 Bible 任务"""
        task = self.db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
        if not task:
            return
        
        self.task_service.update_task_status(task_id, "running", current_step="生成小说 Bible")
        
        steps = [
            ("生成核心卖点", "main"),
            ("生成世界观设定", "main"),
            ("生成主要情节", "main"),
            ("生成人物设定", "main"),
            ("生成力量体系", "main"),
            ("生成关系设定", "main"),
            ("生成文风指南", "main"),
            ("生成禁忌规则", "main"),
        ]
        
        total_steps = len(steps)
        self.task_service.update_task_status(task_id, "running", progress=0, total_steps=total_steps)
        
        bible_service = BibleService(self.db)
        
        for i, (step_name, role) in enumerate(steps):
            step = self.task_service.add_step(task_id, task.novel_id, step_name, i, role)
            self.task_service.update_step(step.id, "running")
            
            try:
                result = bible_service.generate_bible(task.novel_id)
                self.task_service.update_step(step.id, "success", input_prompt=f"生成 {step_name}", parsed_output="已生成")
            except Exception as e:
                self.task_service.update_step(step.id, "failed", error_message=str(e))
                self.task_service.update_task_status(task_id, "failed", current_step=step_name)
                return
            
            progress = int((i + 1) / total_steps * 100)
            self.task_service.update_task_status(task_id, "running", progress=progress)
        
        self.task_service.update_task_status(task_id, "success", current_step="Bible 生成完成", progress=100)

    def run_generate_chapter(self, task_id: int):
        """执行生成下一章任务"""
        task = self.db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
        if not task:
            return
        
        self.task_service.update_task_status(task_id, "running", current_step="开始生成章节")
        
        chapter_service = ChapterService(self.db)
        
        steps = [
            ("生成章节细纲", "main"),
            ("生成章节正文", "main"),
            ("质检评分", "checker"),
            ("润色正文", "editor"),
            ("提取记忆", "memory"),
            ("导出章节", "main"),
        ]
        
        total_steps = len(steps)
        self.task_service.update_task_status(task_id, "running", total_steps=total_steps, progress=0)
        
        try:
            for i, (step_name, role) in enumerate(steps):
                step = self.task_service.add_step(task_id, task.novel_id, step_name, i, role)
                self.task_service.update_step(step.id, "running")
                
                if step_name == "生成章节细纲":
                    chapter_service.generate_next_chapter(task.novel_id)
                
                self.task_service.update_step(step.id, "success")
                progress = int((i + 1) / total_steps * 100)
                self.task_service.update_task_status(task_id, "running", progress=progress, current_step=step_name)
            
            self.task_service.update_task_status(task_id, "success", current_step="章节生成完成", progress=100)
            
        except Exception as e:
            self.task_service.update_task_status(task_id, "failed", current_step=str(e))

    def run_continuous_generate(self, task_id: int, novel_id: int, chapter_count: int):
        """连续生成多章"""
        task = self.db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
        if not task:
            return
        
        self.task_service.update_task_status(task_id, "running", current_step=f"准备连续生成 {chapter_count} 章")
        
        chapter_service = ChapterService(self.db)
        
        for i in range(chapter_count):
            task = self.db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
            if task.status in ["paused", "cancelled"]:
                break
            
            current = i + 1
            self.task_service.update_task_status(
                task_id, 
                "running", 
                current_step=f"正在生成第 {current}/{chapter_count} 章"
            )
            
            try:
                chapter_service.generate_next_chapter(novel_id)
                progress = int((current / chapter_count) * 100)
                self.task_service.update_task_status(task_id, "running", progress=progress)
                
            except Exception as e:
                self.task_service.update_task_status(task_id, "failed", current_step=f"第 {current} 章失败: {str(e)}")
                return
        
        self.task_service.update_task_status(task_id, "success", current_step=f"已完成连续生成 {chapter_count} 章", progress=100)
