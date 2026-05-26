from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Novel, TaskLog, Chapter
from app.services.chapter_service import ChapterService
from app.services.bible_service import BibleService

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@router.get("/novels", response_class=HTMLResponse)
async def novels_page(request: Request, db: Session = Depends(get_db)):
    novels = db.query(Novel).all()
    return templates.TemplateResponse("index.html", {"request": request, "novels": novels})

@router.get("/novels/new", response_class=HTMLResponse)
async def new_novel_form(request: Request):
    return templates.TemplateResponse("novel_form.html", {"request": request})

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
    return templates.TemplateResponse("novel_detail.html", {"request": request, "novel": novel})

@router.post("/novels/{novel_id}/generate-bible")
async def web_generate_bible(novel_id: int, db: Session = Depends(get_db)):
    service = BibleService(db)
    service.generate_bible(novel_id)
    return RedirectResponse(url=f"/novels/{novel_id}", status_code=303)

@router.post("/novels/{novel_id}/generate-next-chapter")
async def web_generate_next_chapter(novel_id: int, db: Session = Depends(get_db)):
    service = ChapterService(db)
    service.generate_next_chapter(novel_id)
    return RedirectResponse(url=f"/novels/{novel_id}", status_code=303)

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

@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, db: Session = Depends(get_db)):
    logs = db.query(TaskLog).order_by(TaskLog.created_at.desc()).limit(50).all()
    return templates.TemplateResponse("logs.html", {"request": request, "logs": logs})

@router.get("/chapters/{chapter_id}", response_class=HTMLResponse)
async def chapter_detail(request: Request, chapter_id: int, db: Session = Depends(get_db)):
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return templates.TemplateResponse("chapter_detail.html", {"request": request, "chapter": chapter})