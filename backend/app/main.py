import asyncio
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


async def warmup_models():
    """
    Pre-warm models and connections to reduce cold-start latency.
    This runs during startup to ensure first requests are fast.
    """
    try:
        from app.services.openai_service import OpenAIService
        from app.utils.model_warmup import warmup_models_on_startup

        logger.info("🔥 Starting model warm-up...")

        # Initialize OpenAI service and warm up
        openai_service = OpenAIService()

        # Warm up HTTP connection pool
        _ = OpenAIService.get_http_client()
        logger.info("✅ HTTP connection pool initialized")

        # Warm up async OpenAI client
        _ = OpenAIService.get_async_client()
        logger.info("✅ Async OpenAI client initialized")

        # Warm up TTS memory cache
        _ = OpenAIService.get_tts_memory_cache()
        logger.info("✅ TTS memory cache initialized")

        # Quick LLM warmup request (if API key available)
        if openai_service.client:
            try:
                warmup_response = await openai_service.generate_completion(
                    prompt="Say 'ready' in one word.",
                    temperature=0.5,
                    max_tokens=5,
                    timeout_s=30.0,
                )
                logger.info(f"✅ LLM warm-up complete: {warmup_response}")
            except Exception as e:
                logger.warning(f"⚠️ LLM warm-up failed (non-critical): {e}")

        logger.info("🔥 Model warm-up complete!")

    except Exception as e:
        logger.warning(f"⚠️ Model warm-up error (non-critical): {e}")


@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Algonox AADOS Backend Started")
    Base.metadata.create_all(bind=engine)
    logger.info("📊 Database tables created/verified")

    # Run model warm-up in background to not block startup
    asyncio.create_task(warmup_models())


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
