from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.routes.web_routes import router as web_router
from app.routes.api_routes import router as api_router
from app.database import engine, Base
from app.services.scheduler_service import start_scheduler
import os

app = FastAPI(
    title="小说自动工厂 API",
    description="自动生成小说设定、章节、质检、润色、记忆和导出的 API 文档",
    version="0.2.0",
    docs_url="/api-docs",
    redoc_url="/redoc"
)

# Ensure static directory exists
os.makedirs("app/static", exist_ok=True)
os.makedirs("app/static/css", exist_ok=True)
os.makedirs("app/static/js", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Include routers (web routes hidden from Swagger)
app.include_router(web_router, include_in_schema=False)
app.include_router(api_router, prefix="/api")

# Startup event
@app.on_event("startup")
async def startup_event():
    # Create tables
    Base.metadata.create_all(bind=engine)
    # Start scheduler
    start_scheduler()
    print("小说自动工厂已启动！")

# Root redirect to novels backend
@app.get("/")
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/novels")