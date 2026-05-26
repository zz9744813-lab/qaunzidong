from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Novel
from app.services.chapter_service import ChapterService
from app.services.bible_service import BibleService

router = APIRouter()

@router.post("/novels/{novel_id}/generate-bible")
def generate_bible(novel_id: int, db: Session = Depends(get_db)):
    service = BibleService()
    bible = service.generate_bible(novel_id)
    return {"message": "Bible generated", "bible_id": bible.id}

@router.post("/novels/{novel_id}/generate-next-chapter")
def generate_next_chapter(novel_id: int, db: Session = Depends(get_db)):
    service = ChapterService()
    chapter = service.generate_next_chapter(novel_id)
    return {"message": "Chapter generated", "chapter_no": chapter.chapter_no}