from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Novel, GenerationTask, NovelBible
from app.services.task_service import TaskService

router = APIRouter()
ACTIVE_TASK_STATUSES = ["pending", "running"]


def _active_task(db: Session, novel_id: int):
    return db.query(GenerationTask).filter(
        GenerationTask.novel_id == novel_id,
        GenerationTask.status.in_(ACTIVE_TASK_STATUSES)
    ).order_by(GenerationTask.id.desc()).first()

@router.post("/novels/{novel_id}/generate-bible")
def generate_bible(novel_id: int, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        return {"message": "Novel not found"}
    active = _active_task(db, novel_id)
    if active:
        return {"message": "Existing task is still active", "task_id": active.id, "status": active.status}
    task = TaskService(db).create_task(novel_id, "generate_bible", total_steps=8)
    return {"message": "Bible task queued", "task_id": task.id}

@router.post("/novels/{novel_id}/generate-next-chapter")
def generate_next_chapter(novel_id: int, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        return {"message": "Novel not found"}
    active = _active_task(db, novel_id)
    if active:
        return {"message": "Existing task is still active", "task_id": active.id, "status": active.status}
    bible = db.query(NovelBible).filter(NovelBible.novel_id == novel_id).first()
    if not bible:
        task = TaskService(db).create_task(novel_id, "generate_bible", total_steps=8)
        return {"message": "Bible is missing; Bible task queued first", "task_id": task.id}
    task = TaskService(db).create_task(novel_id, "generate_chapter", total_steps=7)
    return {"message": "Chapter task queued", "task_id": task.id}

@router.post("/novels/{novel_id}/run-pipeline")
def run_pipeline(novel_id: int, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        return {"message": "Novel not found"}
    active = _active_task(db, novel_id)
    if active:
        return {"message": "Existing task is still active", "task_id": active.id, "status": active.status}
    task = TaskService(db).create_task(novel_id, "run_pipeline", total_steps=9)
    return {"message": "Full pipeline task queued", "task_id": task.id}

@router.post("/novels/{novel_id}/start")
def start_novel(novel_id: int, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if novel:
        novel.status = "running"
        novel.failed_times = 0
        novel.generation_lock = 0
        novel.locked_at = None
        db.commit()
    return {"message": "Novel started"}

@router.post("/novels/{novel_id}/pause")
def pause_novel(novel_id: int, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if novel:
        novel.status = "paused"
        novel.generation_lock = 0
        novel.locked_at = None
        db.commit()
    return {"message": "Novel paused"}
