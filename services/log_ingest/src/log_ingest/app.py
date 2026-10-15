from contextlib import asynccontextmanager

from fastapi import FastAPI

from log_ingest.config import get_settings
from log_ingest.ingest import router as ingest_router
from log_ingest.kafka import check_kafka, create_kafka_producer

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "kafka_producer"):
        app.state.kafka_producer = await create_kafka_producer()
    yield
    producer = getattr(app.state, "kafka_producer", None)
    if producer is not None and hasattr(producer, "stop"):
        await producer.stop()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(ingest_router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": settings.app_name,
        "env": settings.app_env,
    }


@app.get("/health/deep")
async def deep_health():
    kafka_ok = await check_kafka()
    return {
        "status": "ok" if kafka_ok else "degraded",
        "checks": {
            "kafka": kafka_ok,
        },
    }
