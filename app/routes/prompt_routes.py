from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="app/templates")
import os

router = APIRouter()

PROMPTS_DIR = "app/prompts"

def get_prompt_files():
    if not os.path.exists(PROMPTS_DIR):
        return []
    return [f for f in os.listdir(PROMPTS_DIR) if f.endswith('.md')]

@router.get("/prompts", response_class=HTMLResponse)
async def prompts_list(request: Request):
    files = get_prompt_files()
    return templates.TemplateResponse(request, "prompts.html", {"files": files})

@router.get("/prompts/{filename}", response_class=HTMLResponse)
async def prompt_edit(request: Request, filename: str):
    filepath = os.path.join(PROMPTS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404)
    
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    return templates.TemplateResponse(request, "prompt_edit.html", {
        "filename": filename,
        "content": content
    })

@router.post("/prompts/{filename}")
async def prompt_save(filename: str, content: str = Form(...)):
    filepath = os.path.join(PROMPTS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    return RedirectResponse(url="/prompts", status_code=303)

@router.post("/prompts/{filename}/reset")
async def prompt_reset(filename: str):
    # 这里可以实现从默认备份恢复，暂时先返回
    return RedirectResponse(url=f"/prompts/{filename}", status_code=303)
