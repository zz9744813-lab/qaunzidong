"""
真实任务 Worker 服务
每隔几秒从数据库拉取 pending 任务执行，避免依赖 FastAPI BackgroundTasks
"""
import time
import threading
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import GenerationTask, Novel
from app.services.agent_runner import AgentRunner
from loguru import logger

class TaskWorker:
    def __init__(self, poll_interval: int = 5):
        self.poll_interval = poll_interval
        self.running = False
        self.thread = None
    
    def start(self):
        if self.running:
            return
        self.running = True
        self._recover_stale_running_tasks()
        self._recover_orphan_generation_locks()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("TaskWorker 已启动")
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        logger.info("TaskWorker 已停止")
    
    def _run_loop(self):
        while self.running:
            try:
                self._process_pending_tasks()
            except Exception as e:
                logger.error(f"Worker 循环异常: {e}")
            time.sleep(self.poll_interval)

    def _recover_stale_running_tasks(self):
        db: Session = SessionLocal()
        try:
            stale_tasks = db.query(GenerationTask).filter(
                GenerationTask.status == "running"
            ).all()
            for task in stale_tasks:
                task.status = "failed"
                task.error_message = "Task was interrupted by service restart and recovered as failed."
                task.finished_at = datetime.utcnow()
            if stale_tasks:
                db.commit()
                logger.warning(f"Recovered {len(stale_tasks)} stale running task(s)")
        finally:
            db.close()

    def _recover_orphan_generation_locks(self):
        db: Session = SessionLocal()
        try:
            locked_novels = db.query(Novel).filter(Novel.generation_lock == 1).all()
            recovered = 0
            for novel in locked_novels:
                active_task = db.query(GenerationTask).filter(
                    GenerationTask.novel_id == novel.id,
                    GenerationTask.status.in_(["pending", "running"])
                ).first()
                if not active_task:
                    novel.generation_lock = 0
                    novel.locked_at = None
                    recovered += 1
            if recovered:
                db.commit()
                logger.warning(f"Recovered {recovered} orphan generation lock(s)")
        finally:
            db.close()
    
    def _process_pending_tasks(self):
        db: Session = SessionLocal()
        try:
            # 拉取 pending 任务（按创建时间排序）
            pending_tasks = db.query(GenerationTask).filter(
                GenerationTask.status == "pending"
            ).order_by(GenerationTask.created_at.asc()).limit(5).all()
            
            for task in pending_tasks:
                # 跳过已取消的任务
                if task.status == "cancelled":
                    continue
                
                logger.info(f"Worker 接管任务 #{task.id} ({task.task_type})")
                
                # 标记为 running
                task.status = "running"
                task.started_at = datetime.utcnow()
                db.commit()
                
                runner = AgentRunner(db)
                
                try:
                    if task.task_type == "generate_bible":
                        runner.run_generate_bible(task.id)
                    elif task.task_type == "generate_chapter":
                        runner.run_generate_chapter(task.id)
                    elif task.task_type == "run_pipeline":
                        runner.run_full_pipeline(task.id)
                    elif task.task_type == "continuous_generate":
                        # 从任务元数据或默认值获取 chapter_count
                        chapter_count = 3  # 默认值，可后续扩展
                        runner.run_continuous_generate(task.id, task.novel_id, chapter_count)
                    else:
                        logger.warning(f"未知任务类型: {task.task_type}")
                        task.status = "failed"
                        db.commit()
                        
                except Exception as e:
                    logger.error(f"任务 #{task.id} 执行失败: {e}")
                    task.status = "failed"
                    task.error_message = str(e)
                    task.finished_at = datetime.utcnow()
                    db.commit()
                    
        finally:
            db.close()
    
    def retry_failed_task(self, task_id: int):
        """手动重试失败任务"""
        db = SessionLocal()
        try:
            task = db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
            if task and task.status == "failed":
                task.status = "pending"
                task.error_message = None
                db.commit()
                logger.info(f"任务 #{task_id} 已重置为 pending，等待 worker 重试")
        finally:
            db.close()

# 全局 worker 实例
worker = TaskWorker(poll_interval=5)
