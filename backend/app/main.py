import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine

from app.api import (
    leads,
    data_packets,
    calls,
    reports,
    database,
    manual_call,
    websocket,
    analyst,   # ✅ NEW
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("app.main")

app = FastAPI(title="Algonox AADOS Backend", version="1.0.0")


@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Algonox AADOS Backend Started")
    Base.metadata.create_all(bind=engine)
    logger.info("📊 Database tables created/verified")


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(leads.router)
app.include_router(data_packets.router)
app.include_router(calls.router)
app.include_router(reports.router)
app.include_router(database.router)
app.include_router(manual_call.router)
app.include_router(websocket.router)
app.include_router(analyst.router)  # ✅ NEW


@app.get("/")
async def root():
    return {"message": "Algonox AADOS API", "status": "running", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
