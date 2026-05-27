from fastapi import APIRouter, Request, Form, Depends, HTTPException
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
    return templates.TemplateResponse("index.html", {"request": request})

@router.get("/novels", response_class=HTMLResponse)
async def novels_page(request: Request, db: Session = Depends(get_db)):
    novels = db.query(Novel).all()
    
    # 动态统计
    total_chapters = db.query(Chapter).count()
    total_words = db.query(func.sum(Chapter.word_count)).scalar() or 0
    failed_tasks = db.query(TaskLog).filter(TaskLog.status == "failed").count()
    
    stats = {
        "total_novels": len(novels),
        "running_novels": len([n for n in novels if n.status == "running"]),
        "total_chapters": total_chapters,
        "total_words": total_words,
        "failed_tasks": failed_tasks
    }
    
    return templates.TemplateResponse("index.html", {"request": request, "novels": novels, "stats": stats})