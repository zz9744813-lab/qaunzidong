from fastapi import APIRouter, Request, Form, Depends, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Novel, TaskLog, Chapter, GenerationTask, NovelBible, StoryMemory
from app.main import templates
from app.services.chapter_service import ChapterService
from app.services.bible_service import BibleService
from app.services.export_service import ExportService
from datetime import datetime
from urllib.parse import quote
import os

router = APIRouter()
ACTIVE_TASK_STATUSES = ["pending", "running"]


def _latest_task(db: Session, novel_id: int):
    return db.query(GenerationTask).filter(
        GenerationTask.novel_id == novel_id
    ).order_by(GenerationTask.id.desc()).first()


def _active_task(db: Session, novel_id: int):
    return db.query(GenerationTask).filter(
        GenerationTask.novel_id == novel_id,
        GenerationTask.status.in_(ACTIVE_TASK_STATUSES)
    ).order_by(GenerationTask.id.desc()).first()


def _task_redirect(novel_id: int, task_id: int, notice: str = None):
    url = f"/novels/{novel_id}?task_id={task_id}"
    if notice:
        url += f"&notice={quote(notice)}"
    return RedirectResponse(url=url, status_code=303)


def _chapter_export_paths(export_service: ExportService, chapter: Chapter):
    novel_dir = os.path.join(export_service.export_dir, chapter.novel.title.replace(" ", "_"))
    return {
        "md": os.path.join(novel_dir, f"chapter_{chapter.chapter_no:04d}.md"),
        "txt": os.path.join(novel_dir, f"chapter_{chapter.chapter_no:04d}.txt"),
    }

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})

@router.get("/novels", response_class=HTMLResponse)
async def novels_page(request: Request, db: Session = Depends(get_db)):
    novels = db.query(Novel).order_by(Novel.id.desc()).all()
    for novel in novels:
        novel.chapter_count = db.query(Chapter).filter(Chapter.novel_id == novel.id).count()
        novel.has_bible = db.query(NovelBible).filter(NovelBible.novel_id == novel.id).first() is not None
        novel.active_task = _active_task(db, novel.id)
        novel.latest_task = _latest_task(db, novel.id)

    stats = {
        "total_novels": len(novels),
        "running_novels": len([n for n in novels if n.status == "running"]),
        "active_tasks": db.query(GenerationTask).filter(GenerationTask.status.in_(ACTIVE_TASK_STATUSES)).count(),
        "total_chapters": db.query(Chapter).count(),
        "total_words": db.query(func.sum(Chapter.word_count)).scalar() or 0,
        "failed_tasks": db.query(GenerationTask).filter(GenerationTask.status == "failed").count(),
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
    reader_promise: str = Form(""),
    pov_preference: str = Form(""),
    must_have: str = Form(""),
    avoid: str = Form(""),
    target_words: int = Form(1000000),
    chapter_words: int = Form(3500),
    db: Session = Depends(get_db)
):
    details = []
    if description:
        details.append(description)
    if reader_promise:
        details.append(f"读者承诺/核心爽点：{reader_promise}")
    if pov_preference:
        details.append(f"POV 偏好：{pov_preference}")
    if must_have:
        details.append(f"必须包含：{must_have}")
    if avoid:
        details.append(f"禁止/避雷：{avoid}")
    novel = Novel(
        title=title,
        genre=genre,
        style=style,
        description="\n".join(details),
        target_words=max(10000, min(target_words, 10000000)),
        chapter_words=max(800, min(chapter_words, 12000)),
        status="draft"
    )
    db.add(novel)
    db.commit()
    return RedirectResponse(url="/novels", status_code=303)

@router.get("/novels/{novel_id}", response_class=HTMLResponse)
async def novel_detail(request: Request, novel_id: int, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    novel.chapters = db.query(Chapter).filter(
        Chapter.novel_id == novel_id
    ).order_by(Chapter.chapter_no.asc()).all()
    final_chapters = [chapter for chapter in novel.chapters if chapter.status == "final"]
    bible = db.query(NovelBible).filter(NovelBible.novel_id == novel_id).first()
    active_task = _active_task(db, novel_id)
    recent_tasks = db.query(GenerationTask).filter(
        GenerationTask.novel_id == novel_id
    ).order_by(GenerationTask.id.desc()).limit(8).all()
    latest_task = recent_tasks[0] if recent_tasks else None
    latest_steps = sorted(latest_task.steps, key=lambda step: step.step_order) if latest_task else []
    latest_chapter = final_chapters[-1] if final_chapters else None
    latest_export = None
    if latest_chapter:
        export_service = ExportService(db)
        export_path = export_service.export_chapter(latest_chapter.id)
        paths = _chapter_export_paths(export_service, latest_chapter)
        latest_export = {
            "chapter": latest_chapter,
            "path": export_path,
            "md_exists": os.path.exists(paths["md"]),
            "txt_exists": os.path.exists(paths["txt"]),
            "md_path": paths["md"],
            "txt_path": paths["txt"],
            "preview": (latest_chapter.final_text or latest_chapter.draft_text or "")[:2200],
        }
    memories = db.query(StoryMemory).filter(
        StoryMemory.novel_id == novel_id
    ).order_by(StoryMemory.created_at.desc()).limit(60).all()
    memory_groups = {}
    for memory in memories:
        memory_groups.setdefault(memory.memory_type or "other", []).append(memory)
    unresolved_foreshadowing = db.query(StoryMemory).filter(
        StoryMemory.novel_id == novel_id,
        StoryMemory.memory_type == "foreshadowing",
        StoryMemory.is_resolved == 0
    ).order_by(StoryMemory.importance.desc(), StoryMemory.created_at.desc()).limit(12).all()
    pov_memories = db.query(StoryMemory).filter(
        StoryMemory.novel_id == novel_id,
        StoryMemory.memory_type.in_(["pov_state", "character_goal", "character_change"])
    ).order_by(StoryMemory.created_at.desc()).limit(12).all()
    stats = {
        "chapter_count": len(final_chapters),
        "bible_words": len(bible.full_text or "") if bible else 0,
        "latest_task": recent_tasks[0] if recent_tasks else None,
        "memory_count": db.query(StoryMemory).filter(StoryMemory.novel_id == novel_id).count(),
        "foreshadowing_count": len(unresolved_foreshadowing),
    }
    return templates.TemplateResponse(
        request,
        "novel_detail.html",
        {
            "request": request,
            "novel": novel,
            "bible": bible,
            "active_task": active_task,
            "recent_tasks": recent_tasks,
            "latest_task": latest_task,
            "latest_steps": latest_steps,
            "latest_export": latest_export,
            "final_chapters": final_chapters,
            "memories": memories,
            "memory_groups": memory_groups,
            "unresolved_foreshadowing": unresolved_foreshadowing,
            "pov_memories": pov_memories,
            "stats": stats,
        },
    )

@router.post("/novels/{novel_id}/generate-bible")
async def web_generate_bible(novel_id: int, db: Session = Depends(get_db)):
    from app.services.task_service import TaskService
    
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(status_code=404)
    active = _active_task(db, novel_id)
    if active:
        return _task_redirect(novel_id, active.id, "已有任务正在执行，已打开当前任务")

    task_service = TaskService(db)
    task = task_service.create_task(novel_id, "generate_bible", total_steps=8)
    return _task_redirect(novel_id, task.id, "Bible 任务已提交")

@router.post("/novels/{novel_id}/generate-next-chapter")
async def web_generate_next_chapter(novel_id: int, db: Session = Depends(get_db)):
    from app.services.task_service import TaskService
    
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(status_code=404)
    active = _active_task(db, novel_id)
    if active:
        return _task_redirect(novel_id, active.id, "已有任务正在执行，已打开当前任务")

    task_service = TaskService(db)
    bible = db.query(NovelBible).filter(NovelBible.novel_id == novel_id).first()
    if not bible:
        task = task_service.create_task(novel_id, "generate_bible", total_steps=8)
        return _task_redirect(novel_id, task.id, "还没有 Bible，已先提交 Bible 任务")

    task = task_service.create_task(novel_id, "generate_chapter", total_steps=7)
    return _task_redirect(novel_id, task.id, "章节任务已提交")


@router.post("/novels/{novel_id}/run-pipeline")
async def web_run_pipeline(novel_id: int, db: Session = Depends(get_db)):
    from app.services.task_service import TaskService

    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(status_code=404)
    active = _active_task(db, novel_id)
    if active:
        return _task_redirect(novel_id, active.id, "已有任务正在执行，已打开当前任务")

    task = TaskService(db).create_task(novel_id, "run_pipeline", total_steps=9)
    return _task_redirect(novel_id, task.id, "完整生产线已提交")

@router.post("/novels/{novel_id}/start")
async def web_start_novel(novel_id: int, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if novel:
        novel.status = "running"
        novel.failed_times = 0
        novel.generation_lock = 0
        novel.locked_at = None
    db.commit()
    return RedirectResponse(url=f"/novels/{novel_id}", status_code=303)

@router.post("/novels/{novel_id}/pause")
async def web_pause_novel(novel_id: int, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if novel:
        novel.status = "paused"
        novel.generation_lock = 0
        novel.locked_at = None
    db.commit()
    return RedirectResponse(url=f"/novels/{novel_id}", status_code=303)

@router.post("/novels/{novel_id}/export-full")
async def web_export_full(novel_id: int, db: Session = Depends(get_db)):
    service = ExportService(db)
    path = service.export_full_novel(novel_id, format="markdown")
    if path and os.path.exists(path):
        return FileResponse(path, filename=os.path.basename(path))
    return RedirectResponse(url=f"/novels/{novel_id}", status_code=303)


@router.get("/novels/{novel_id}/export-full/{file_format}")
async def web_export_full_format(novel_id: int, file_format: str, db: Session = Depends(get_db)):
    if file_format not in {"md", "txt"}:
        raise HTTPException(status_code=404, detail="Unsupported export format")
    service = ExportService(db)
    path = service.export_full_novel(novel_id, format="markdown" if file_format == "md" else "txt")
    if path and os.path.exists(path):
        return FileResponse(path, filename=os.path.basename(path))
    raise HTTPException(status_code=404, detail="Export file not found")


@router.get("/novels/{novel_id}/read", response_class=HTMLResponse)
async def novel_reader(request: Request, novel_id: int, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    chapters = db.query(Chapter).filter(
        Chapter.novel_id == novel_id,
        Chapter.status == "final"
    ).order_by(Chapter.chapter_no.asc()).all()
    export_service = ExportService(db)
    full_md = export_service.export_full_novel(novel_id, format="markdown") if chapters else ""
    full_txt = export_service.export_full_novel(novel_id, format="txt") if chapters else ""
    return templates.TemplateResponse(
        request,
        "novel_read.html",
        {
            "request": request,
            "novel": novel,
            "chapters": chapters,
            "full_md": full_md,
            "full_txt": full_txt,
        },
    )

@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, db: Session = Depends(get_db)):
    logs = db.query(TaskLog).order_by(TaskLog.created_at.desc()).limit(50).all()
    return templates.TemplateResponse(request, "logs.html", {"request": request, "logs": logs})

@router.get("/chapters/{chapter_id}", response_class=HTMLResponse)
async def chapter_detail(request: Request, chapter_id: int, db: Session = Depends(get_db)):
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    export_service = ExportService(db)
    export_path = export_service.export_chapter(chapter.id) if chapter.final_text or chapter.draft_text else ""
    paths = _chapter_export_paths(export_service, chapter)
    return templates.TemplateResponse(
        request,
        "chapter_detail.html",
        {
            "request": request,
            "chapter": chapter,
            "novel": chapter.novel,
            "export_path": export_path,
            "md_path": paths["md"],
            "txt_path": paths["txt"],
            "md_exists": os.path.exists(paths["md"]),
            "txt_exists": os.path.exists(paths["txt"]),
        },
    )


@router.get("/chapters/{chapter_id}/export/{file_format}")
async def chapter_export(chapter_id: int, file_format: str, db: Session = Depends(get_db)):
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    if file_format not in {"md", "txt"}:
        raise HTTPException(status_code=404, detail="Unsupported export format")
    export_service = ExportService(db)
    export_service.export_chapter(chapter.id)
    path = _chapter_export_paths(export_service, chapter)[file_format]
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Export file not found")
    return FileResponse(path, filename=os.path.basename(path))

@router.get("/tasks/{task_id}", response_class=HTMLResponse)
async def task_detail(request: Request, task_id: int, db: Session = Depends(get_db)):
    from app.services.task_service import TaskService
    task_service = TaskService(db)
    task = task_service.get_task_with_steps(task_id)
    if not task:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "task_detail.html", {"request": request, "task": task})


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
                "step_order": s.step_order,
                "step_name": s.step_name,
                "status": s.status,
                "provider_role": s.provider_role,
                "model_name": s.model_name,
                "input_prompt": s.input_prompt,
                "raw_output": s.raw_output,
                "parsed_output": s.parsed_output,
                "error_message": s.error_message,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
            }
            for s in task.steps
        ]
    }




@router.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: int, db: Session = Depends(get_db)):
    from app.services.task_service import TaskService
    task_service = TaskService(db)
    task = task_service.get_task_with_steps(task_id)
    if not task:
        raise HTTPException(status_code=404)
    
    if task.status in ["pending", "running"]:
        task.status = "cancelled"
        task.error_message = "用户手动取消"
        task.finished_at = datetime.utcnow()
        db.commit()
    return {"status": "cancelled"}


@router.post("/api/tasks/{task_id}/retry")
async def retry_task(task_id: int, db: Session = Depends(get_db)):
    from app.services.task_service import TaskService
    task_service = TaskService(db)
    task = task_service.get_task_with_steps(task_id)
    if not task:
        raise HTTPException(status_code=404)
    
    active = _active_task(db, task.novel_id)
    if active:
        return {"status": active.status, "task_id": active.id}

    if task.status in ["failed", "cancelled"]:
        from app.services.task_service import TaskService
        task_service = TaskService(db)
        new_task = task_service.create_task(
            task.novel_id,
            task.task_type,
            total_steps=task.total_steps,
            chapter_id=task.chapter_id,
        )
        return {"status": "pending", "task_id": new_task.id}
    return {"status": task.status, "task_id": task.id}


@router.post("/novels/{novel_id}/continuous-generate")
async def continuous_generate(
    novel_id: int,
    chapter_count: int = Form(...),
    db: Session = Depends(get_db)
):
    from app.services.task_service import TaskService
    
    active = _active_task(db, novel_id)
    if active:
        return _task_redirect(novel_id, active.id, "已有任务正在执行，已打开当前任务")

    task_service = TaskService(db)
    bible = db.query(NovelBible).filter(NovelBible.novel_id == novel_id).first()
    if not bible:
        task = task_service.create_task(novel_id, "generate_bible", total_steps=8)
        return _task_redirect(novel_id, task.id, "还没有 Bible，已先提交 Bible 任务")

    chapter_count = max(1, min(chapter_count, 20))
    task = task_service.create_task(novel_id, "continuous_generate", total_steps=chapter_count * 7)
    return _task_redirect(novel_id, task.id, "连续生成任务已提交")
