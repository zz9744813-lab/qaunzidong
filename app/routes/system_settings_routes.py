from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AppSetting
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="app/templates")

router = APIRouter()

DEFAULT_SETTINGS = {
    "writing.default_chapter_words": "3500",
    "writing.min_quality_score": "80",
    "writing.max_rewrite_times": "2",
    "writing.auto_polish": "true",
    "writing.auto_memory_extract": "true",
    "scheduler.interval_minutes": "10",
    "scheduler.max_chapters_per_day": "10",
    "scheduler.max_failed_times": "5",
    "export.export_dir": "data/exports",
}

@router.get("/settings/system", response_class=HTMLResponse)
async def system_settings(request: Request, db: Session = Depends(get_db)):
    settings = {}
    for key, default in DEFAULT_SETTINGS.items():
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        settings[key] = setting.value if setting else default
    
    return templates.TemplateResponse(request, "settings_system.html", {"settings": settings})

@router.post("/settings/system")
async def save_system_settings(
    default_chapter_words: str = Form(...),
    min_quality_score: str = Form(...),
    max_rewrite_times: str = Form(...),
    auto_polish: str = Form("false"),
    auto_memory_extract: str = Form("false"),
    interval_minutes: str = Form(...),
    max_chapters_per_day: str = Form(...),
    max_failed_times: str = Form(...),
    export_dir: str = Form(...),
    db: Session = Depends(get_db)
):
    updates = {
        "writing.default_chapter_words": default_chapter_words,
        "writing.min_quality_score": min_quality_score,
        "writing.max_rewrite_times": max_rewrite_times,
        "writing.auto_polish": auto_polish,
        "writing.auto_memory_extract": auto_memory_extract,
        "scheduler.interval_minutes": interval_minutes,
        "scheduler.max_chapters_per_day": max_chapters_per_day,
        "scheduler.max_failed_times": max_failed_times,
        "export.export_dir": export_dir,
    }
    
    for key, value in updates.items():
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if setting:
            setting.value = value
        else:
            setting = AppSetting(key=key, value=value)
            db.add(setting)
    
    db.commit()
    return RedirectResponse(url="/settings/system", status_code=303)
