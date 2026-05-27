from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import LLMProvider
from app.main import templates
import os
import requests

router = APIRouter()

@router.get("/settings/llm", response_class=HTMLResponse)
async def llm_settings(request: Request, db: Session = Depends(get_db)):
    providers = db.query(LLMProvider).order_by(LLMProvider.role, LLMProvider.id).all()
    return templates.TemplateResponse(request, "settings_llm.html", {"providers": providers})

@router.get("/settings/llm/new", response_class=HTMLResponse)
async def new_llm_provider(request: Request):
    return templates.TemplateResponse(request, "settings_llm_form.html", {"provider": None})

@router.post("/settings/llm/new")
async def create_llm_provider(
    name: str = Form(...),
    role: str = Form(...),
    base_url: str = Form(...),
    api_key: str = Form(...),
    model: str = Form(...),
    temperature: str = Form("0.85"),
    max_tokens: int = Form(8000),
    timeout_seconds: int = Form(180),
    retry_times: int = Form(3),
    db: Session = Depends(get_db)
):
    provider = LLMProvider(
        name=name,
        role=role,
        base_url=base_url,
        api_key_encrypted=api_key,  # TODO: 加密
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
        retry_times=retry_times,
        enabled=1
    )
    db.add(provider)
    db.commit()
    return RedirectResponse(url="/settings/llm", status_code=303)

@router.get("/settings/llm/{provider_id}/edit", response_class=HTMLResponse)
async def edit_llm_provider(provider_id: int, request: Request, db: Session = Depends(get_db)):
    provider = db.query(LLMProvider).filter(LLMProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "settings_llm_form.html", {"provider": provider})

@router.post("/settings/llm/{provider_id}/edit")
async def update_llm_provider(
    provider_id: int,
    name: str = Form(...),
    role: str = Form(...),
    base_url: str = Form(...),
    api_key: str = Form(...),
    model: str = Form(...),
    temperature: str = Form("0.85"),
    max_tokens: int = Form(8000),
    timeout_seconds: int = Form(180),
    retry_times: int = Form(3),
    db: Session = Depends(get_db)
):
    provider = db.query(LLMProvider).filter(LLMProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404)
    
    provider.name = name
    provider.role = role
    provider.base_url = base_url
    if api_key and api_key != "********":  # 只有用户修改时才更新
        from app.utils import encrypt_api_key
        provider.api_key_encrypted = encrypt_api_key(api_key)
    provider.model = model
    provider.temperature = temperature
    provider.max_tokens = max_tokens
    provider.timeout_seconds = timeout_seconds
    provider.retry_times = retry_times
    db.commit()
    return RedirectResponse(url="/settings/llm", status_code=303)

@router.post("/settings/llm/{provider_id}/delete")
async def delete_llm_provider(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(LLMProvider).filter(LLMProvider.id == provider_id).first()
    if provider:
        db.delete(provider)
        db.commit()
    return RedirectResponse(url="/settings/llm", status_code=303)

@router.post("/settings/llm/{provider_id}/toggle")
async def toggle_llm_provider(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(LLMProvider).filter(LLMProvider.id == provider_id).first()
    if provider:
        provider.enabled = 0 if provider.enabled else 1
        db.commit()
    return RedirectResponse(url="/settings/llm", status_code=303)

@router.post("/settings/llm/{provider_id}/test")
async def test_llm_provider(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(LLMProvider).filter(LLMProvider.id == provider_id).first()
    if not provider:
        return JSONResponse({"success": False, "message": "配置不存在"}, status_code=404)
    
    try:
        headers = {
            from app.utils import decrypt_api_key
            "Authorization": f"Bearer {decrypt_api_key(provider.api_key_encrypted)}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": provider.model,
            "messages": [{"role": "user", "content": "请只回复 OK，不要输出其他内容。"}],
            "max_tokens": 10
        }
        
        response = requests.post(
            f"{provider.base_url.rstrip('/')}/chat/completions",
            json=payload,
            headers=headers,
            timeout=provider.timeout_seconds or 30
        )
        
        if response.status_code == 200:
            return JSONResponse({
                "success": True, 
                "message": "连接成功",
                "model": provider.model
            })
        else:
            return JSONResponse({
                "success": False, 
                "message": f"HTTP {response.status_code}",
                "detail": response.text[:500]
            }, status_code=400)
            
    except Exception as e:
        return JSONResponse({
            "success": False, 
            "message": str(e)
        }, status_code=400)
