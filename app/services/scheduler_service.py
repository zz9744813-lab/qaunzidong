from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.database import SessionLocal
from app.models import Novel, Chapter
from app.services.chapter_service import ChapterService
from app.config import settings
from loguru import logger
import threading
from datetime import date, datetime

scheduler = BackgroundScheduler()
running_novels = set()
lock = threading.Lock()

def auto_generate_job():
    db = SessionLocal()
    try:
        running_novels_list = db.query(Novel).filter(Novel.status == "running").all()
        for novel in running_novels_list:
            with lock:
                if novel.id in running_novels:
                    continue
                running_novels.add(novel.id)

            try:
                # 检查今日已生成章节数
                today = date.today()
                today_chapters = db.query(Chapter).filter(
                    Chapter.novel_id == novel.id,
                    Chapter.created_at >= today
                ).count()

                max_daily = settings.scheduler.get("max_chapters_per_day", 10)
                if today_chapters >= max_daily:
                    logger.info(f"Novel {novel.id} reached daily limit ({max_daily})")
                    continue

                chapter_service = ChapterService(db)
                chapter_service.generate_next_chapter(novel.id)
                logger.info(f"Auto generated chapter for novel {novel.id}")
            except Exception as e:
                logger.error(f"Auto generate failed for novel {novel.id}: {str(e)}")
                novel.failed_times = (novel.failed_times or 0) + 1
                if novel.failed_times >= settings.scheduler.get("max_failed_times", 5):
                    novel.status = "paused"
                db.commit()
            finally:
                with lock:
                    running_novels.discard(novel.id)
    finally:
        db.close()

def start_scheduler():
    scheduler.add_job(
        auto_generate_job,
        trigger=IntervalTrigger(minutes=settings.scheduler.get("interval_minutes", 10)),
        id="auto_novel_generator",
        replace_existing=True
    )
    scheduler.start()
    logger.info("Scheduler started")