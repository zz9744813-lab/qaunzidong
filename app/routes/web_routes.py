from fastapi import APIRouter, Request, Form, Depends, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Novel, TaskLog, Chapter
from app.main import templates
from app.services.chapter_service import ChapterService
from app.services.bible_service import BibleService
from app.services.export_service import ExportService
import os

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})

@router.get("/novels", response_class=HTMLResponse)
async def novels_page(request: Request, db: Session = Depends(get_db)):
    novels = db.query(Novel).all()
    stats = {
        "total_novels": len(novels),
        "running_novels": len([n for n in novels if n.status == "running"]),
        "total_chapters": db.query(Chapter).count(),
        "total_words": db.query(func.sum(Chapter.word_count)).scalar() or 0,
        "failed_tasks": db.query(TaskLog).filter(TaskLog.status == "failed").count(),
    }
    return templates.TemplateResponse(
        request, "index.html", {"request": request, "novels": novels, "stats": stats}
    )

@router.get("/novels/new", response_class=HTMLResponse)
async def new_novel_form(request: Request):
    return templates.TemplateResponse(request, "novel_form.html", {"request": request})

@router.post("/novels/new")
async def create_novel(
    title: str = Form(...),
    genre: str = Form(...),
    style: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db)
):
    novel = Novel(
        title=title,
        genre=genre,
        style=style,
        description=description,
        status="draft"
    )
    db.add(novel)
    db.commit()
    return RedirectResponse(url="/novels", status_code=303)

@router.get("/novels/{novel_id}", response_class=HTMLResponse)
async def novel_detail(request: Request, novel_id: int, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    # 加载章节（如果模型支持）
    if novel:
        novel.chapters = db.query(Chapter).filter(Chapter.novel_id == novel_id).all()
    return templates.TemplateResponse(request, "novel_detail.html", {"request": request, "novel": novel})

@router.post("/novels/{novel_id}/generate-bible")
async def web_generate_bible(novel_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    from app.services.task_service import TaskService
    from app.database import SessionLocal
    
    task_service = TaskService(db)
    task = task_service.create_task(novel_id, "generate_bible", total_steps=8)
    
    # 使用 BackgroundTasks 后台执行（必须创建独立 session，避免请求结束后 session 被关闭）
    def run_bible_task():
        db_session = SessionLocal()
        try:
            from app.services.agent_runner import AgentRunner
            runner = AgentRunner(db_session)
            runner.run_generate_bible(task.id)
        finally:
            db_session.close()
    
    background_tasks.add_task(run_bible_task)
    
    return RedirectResponse(url=f"/novels/{novel_id}?task_id={task.id}", status_code=303)

@router.post("/novels/{novel_id}/generate-next-chapter")
async def web_generate_next_chapter(novel_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    from app.services.task_service import TaskService
    from app.database import SessionLocal
    
    task_service = TaskService(db)
    task = task_service.create_task(novel_id, "generate_chapter", total_steps=6)
    
    def run_chapter_task():
        db_session = SessionLocal()
        try:
            from app.services.agent_runner import AgentRunner
            runner = AgentRunner(db_session)
            runner.run_generate_chapter(task.id)
        finally:
            db_session.close()
    
    background_tasks.add_task(run_chapter_task)
    
    return RedirectResponse(url=f"/novels/{novel_id}?task_id={task.id}", status_code=303)

@router.post("/novels/{novel_id}/start")
async def web_start_novel(novel_id: int, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if novel:
        novel.status = "running"
    db.commit()
    return RedirectResponse(url=f"/novels/{novel_id}", status_code=303)

@router.post("/novels/{novel_id}/pause")
async def web_pause_novel(novel_id: int, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if novel:
        novel.status = "paused"
    db.commit()
    return RedirectResponse(url=f"/novels/{novel_id}", status_code=303)

@router.post("/novels/{novel_id}/export-full")
async def web_export_full(novel_id: int, db: Session = Depends(get_db)):
    service = ExportService(db)
    path = service.export_full_novel(novel_id, format="markdown")
    if path and os.path.exists(path):
        return FileResponse(path, filename=os.path.basename(path))
    return RedirectResponse(url=f"/novels/{novel_id}", status_code=303)

@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, db: Session = Depends(get_db)):
    logs = db.query(TaskLog).order_by(TaskLog.created_at.desc()).limit(50).all()
    return templates.TemplateResponse(request, "logs.html", {"request": request, "logs": logs})

@router.get("/chapters/{chapter_id}", response_class=HTMLResponse)
async def chapter_detail(request: Request, chapter_id: int, db: Session = Depends(get_db)):
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return templates.TemplateResponse(request, "chapter_detail.html", {"request": request, "chapter": chapter, "novel": chapter.novel})

@router.get("/tasks/{task_id}", response_class=HTMLResponse)
async def task_detail(request: Request, task_id: int, db: Session = Depends(get_db)):
    from app.services.task_service import TaskService
    task_service = TaskService(db)
    task = task_service.get_task_with_steps(task_id)
    if not task:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "task_detail.html", {"task": task})


@router.get("/api/tasks/{task_id}")
async def get_task_status(task_id: int, db: Session = Depends(get_db)):
    from app.services.task_service import TaskService
    task_service = TaskService(db)
    task = task_service.get_task_with_steps(task_id)
    if not task:
        raise HTTPException(status_code=404)
    
    return {
        "id": task.id,
        "status": task.status,
        "current_step": task.current_step,
        "progress": task.progress,
        "total_steps": task.total_steps,
        "finished_steps": task.finished_steps,
        "error_message": task.error_message,
        "steps": [
            {
                "id": s.id,
                "step_name": s.step_name,
                "status": s.status,
                "provider_role": s.provider_role,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
            }
            for s in task.steps
        ]
    }


@router.post("/novels/{novel_id}/continuous-generate")
async def continuous_generate(
    novel_id: int,
    chapter_count: int = Form(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    from app.services.task_service import TaskService
    from app.database import SessionLocal
    
    task_service = TaskService(db)
    task = task_service.create_task(novel_id, "continuous_generate", total_steps=chapter_count * 6)
    
    if background_tasks:
        def run_continuous_bg():
            db_session = SessionLocal()
            try:
                from app.services.agent_runner import AgentRunner
                runner = AgentRunner(db_session)
                runner.run_continuous_generate(task.id, novel_id, chapter_count)
            finally:
                db_session.close()
        background_tasks.add_task(run_continuous_bg)
    else:
        # 兜底同步执行（不推荐）- 也使用独立 session
        db_session = SessionLocal()
        try:
            from app.services.agent_runner import AgentRunner
            runner = AgentRunner(db_session)
            runner.run_continuous_generate(task.id, novel_id, chapter_count)
        finally:
            db_session.close()
    
    return RedirectResponse(url=f"/novels/{novel_id}?task_id={task.id}", status_code=303)
