from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/novels", response_class=HTMLResponse)
async def novels_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "novels": []})

@router.get("/novels/{novel_id}", response_class=HTMLResponse)
async def novel_detail(request: Request, novel_id: int):
    return templates.TemplateResponse("novel_detail.html", {"request": request, "novel": None})