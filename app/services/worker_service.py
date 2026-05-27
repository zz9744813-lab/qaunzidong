"""
真实任务 Worker 服务
每隔几秒从数据库拉取 pending 任务执行，避免依赖 FastAPI BackgroundTasks
"""
import time
import threading
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import GenerationTask
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
                    elif task.task_type == "continuous_generate":
                        # continuous_generate 需要额外参数，暂时跳过或从任务元数据读取
                        logger.warning(f"continuous_generate 暂未在 worker 中实现 task_id={task.id}")
                        task.status = "failed"
                        task.error_message = "continuous_generate 暂不支持 worker 执行"
                        db.commit()
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
