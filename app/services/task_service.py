from sqlalchemy.orm import Session
from app.models import GenerationTask, GenerationStep
from datetime import datetime

class TaskService:
    def __init__(self, db: Session):
        self.db = db

    def create_task(self, novel_id: int, task_type: str, total_steps: int = 0, chapter_id: int = None) -> GenerationTask:
        task = GenerationTask(
            novel_id=novel_id,
            chapter_id=chapter_id,
            task_type=task_type,
            status="pending",
            total_steps=total_steps,
            progress=0
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def update_task_status(self, task_id: int, status: str, current_step: str = None, progress: int = None, total_steps: int = None):
        task = self.db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
        if not task:
            return None
        
        task.status = status
        if current_step:
            task.current_step = current_step
        if progress is not None:
            task.progress = progress
        if total_steps is not None:
            task.total_steps = total_steps
        
        if status == "running" and not task.started_at:
            task.started_at = datetime.utcnow()
        if status in ["success", "failed", "cancelled"]:
            task.finished_at = datetime.utcnow()
        
        self.db.commit()
        return task

    def add_step(self, task_id: int, novel_id: int, step_name: str, step_order: int, 
                 provider_role: str = None, chapter_id: int = None) -> GenerationStep:
        step = GenerationStep(
            task_id=task_id,
            novel_id=novel_id,
            chapter_id=chapter_id,
            step_name=step_name,
            step_order=step_order,
            status="pending",
            provider_role=provider_role
        )
        self.db.add(step)
        self.db.commit()
        self.db.refresh(step)
        return step

    def update_step(self, step_id: int, status: str, input_prompt: str = None, 
                    raw_output: str = None, parsed_output: str = None, error_message: str = None):
        step = self.db.query(GenerationStep).filter(GenerationStep.id == step_id).first()
        if not step:
            return None
        
        step.status = status
        if input_prompt:
            step.input_prompt = input_prompt
        if raw_output:
            step.raw_output = raw_output
        if parsed_output:
            step.parsed_output = parsed_output
        if error_message:
            step.error_message = error_message
        
        if status == "running":
            step.started_at = datetime.utcnow()
        if status in ["success", "failed", "skipped"]:
            step.finished_at = datetime.utcnow()
        
        self.db.commit()
        return step

    def get_task_with_steps(self, task_id: int):
        task = self.db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
        if task:
            task.steps = self.db.query(GenerationStep).filter(
                GenerationStep.task_id == task_id
            ).order_by(GenerationStep.step_order).all()
        return task
