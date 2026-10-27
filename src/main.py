import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from src import metrics
from src.api.auth_routes import router as auth_router
from src.api.database_routes import router as database_router
from src.api.routes import router
from src.config import get_settings
from src.logging_config import configure_logging
from src.services import ingest_watcher

settings = get_settings()
configure_logging(settings.log_level)
_access_logger = logging.getLogger("access")

if settings.langchain_tracing_enabled:
    # LangChain tracer đọc các biến này từ os.environ mỗi lần 1 chain/graph
    # thực sự chạy (lazy, không bake vào graph đã compile lúc import) — chỉ
    # cần set trước khi request đầu tiên tới, không cần trước import
    # src.agents.graph. Tắt mặc định (xem src/config.py) nên không âm thầm
    # gửi trace khi ai đó chạy pytest/dev server mà chưa cố ý bật.
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langchain_endpoint


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Starting {settings.app_name} in {settings.app_env} mode")
    watcher_task: asyncio.Task | None = None
    if settings.auto_reingest_enabled:
        watcher_task = asyncio.create_task(ingest_watcher.run_forever())
    yield
    if watcher_task is not None:
        watcher_task.cancel()
    print("Shutting down...")


app = FastAPI(
    title="AI20K Agent",
    description="AI Agent built with LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    # Metric dùng ROUTE TEMPLATE (/api/v1/assets/{asset_id}) chứ không dùng
    # URL thật: nhãn path mà mang ID thì mỗi ID sinh 1 time series riêng trong
    # Prometheus — vài nghìn asset thành vài nghìn series cho đúng 1 endpoint.
    # Request không khớp route nào (404, bot quét URL ngẫu nhiên) gom hết vào
    # "unmatched", để người ngoài không bơm được series mới vào Prometheus chỉ
    # bằng cách gọi URL lạ.
    route = request.scope.get("route")
    metric_path = getattr(route, "path", None) or "unmatched"
    metrics.record_request(request.method, metric_path, response.status_code, duration_ms)
    # Access log vẫn ghi URL thật (debug cần biết chính xác ID nào lỗi), và
    # truyền field qua extra= để JsonFormatter đẩy lên JSON cấp 1 — Loki query
    # được `| json | status >= 500` thay vì phải parse chuỗi lồng trong chuỗi.
    _access_logger.info(
        "http_request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "route": metric_path,
            "status": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


app.include_router(router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(database_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}


@app.get("/metrics")
async def metrics_endpoint():
    return Response(content=metrics.render_prometheus_text(), media_type="text/plain")
