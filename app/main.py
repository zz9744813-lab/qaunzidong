from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.routes.web_routes import router as web_router
from app.routes.api_routes import router as api_router
from app.database import engine, Base
from app.services.scheduler_service import start_scheduler
import os

app = FastAPI(title="Novel Auto Factory")

# Ensure static directory exists
os.makedirs("app/static", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Include routers
app.include_router(web_router)
app.include_router(api_router, prefix="/api")

# Startup event
@app.on_event("startup")
async def startup_event():
    # Create tables
    Base.metadata.create_all(bind=engine)
    # Start scheduler
    start_scheduler()
    print("Novel Auto Factory started successfully!")

# Root redirect
@app.get("/")
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/novels")