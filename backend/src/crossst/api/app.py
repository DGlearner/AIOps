from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from crossst.api.routes.analysis import router as analysis_router
from crossst.api.routes.chat import router as chat_router
from crossst.api.routes.diagnosis import router as diagnosis_router
from crossst.api.routes.ops import router as ops_router
from crossst.core.config import get_settings
from crossst.infrastructure.storage.kafka import check_kafka
from crossst.infrastructure.storage.postgres import check_postgres, close_postgres
from crossst.infrastructure.storage.redis import check_redis, close_redis

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_redis()
    await close_postgres()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis_router)
app.include_router(diagnosis_router)
app.include_router(ops_router)
app.include_router(chat_router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": settings.app_name,
        "env": settings.app_env,
    }


@app.get("/health/deep")
async def deep_health():
    checks = {
        "postgres": await check_postgres(),
        "redis": await check_redis(),
        "kafka": await check_kafka(),
    }

    return {
        "status": "ok" if all(checks.values()) else "degraded",
        "checks": checks,
    }

