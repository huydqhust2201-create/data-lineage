"""Tự động re-ingest khi phát hiện file .sql thay đổi (mtime mới hơn lần
ingest gần nhất) — giải quyết "tự động cập nhật khi code thay đổi" mà không
cần user chủ động bấm nút ingest lại mỗi lần.

Chỉ hoạt động với ingest theo path server bền vững (POST /ingest) — path
upload là thư mục tạm bị xoá ngay sau request, tự bị bỏ qua vì Path(...).exists()
trả về False lúc watcher chạy. Tắt mặc định (settings.auto_reingest_enabled)
— bật qua .env khi cần demo, xem src/config.py.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from src.config import get_settings
from src.services import ingest_service, storage_service

logger = logging.getLogger(__name__)


def _has_sql_file_changed_since(input_path: str, since: datetime) -> bool:
    root = Path(input_path)
    if not root.exists():
        return False
    for sql_file in root.rglob("*.sql"):
        try:
            mtime = datetime.fromtimestamp(sql_file.stat().st_mtime, UTC)
        except OSError:
            continue
        if mtime > since:
            return True
    return False


async def check_and_reingest_stale_paths() -> list[dict]:
    """Với mỗi database, lấy lượt ingest gần nhất — nếu path đó vẫn tồn tại
    trên đĩa (không phải thư mục upload tạm đã bị xoá) và có file .sql mới
    hơn lượt ingest đó, tự động ingest lại. Trả về danh sách database đã tự
    re-ingest (dùng để log/test) — 1 lần gọi, không tự lặp lại.
    """
    reingested: list[dict] = []
    for database_id in storage_service.list_all_database_ids():
        runs = storage_service.list_ingest_runs(database_id, limit=1)
        if not runs:
            continue
        latest = runs[0]
        if not _has_sql_file_changed_since(latest.input_path, latest.started_at):
            continue
        try:
            await ingest_service.run_ingest(latest.input_path, database_id, None)
            reingested.append({"database_id": database_id, "input_path": latest.input_path})
            logger.info("auto_reingest: re-ingested database_id=%s path=%s", database_id, latest.input_path)
        except Exception:
            logger.exception(
                "auto_reingest: failed for database_id=%s path=%s", database_id, latest.input_path
            )
    return reingested


async def run_forever() -> None:
    """Vòng lặp nền — chỉ start khi settings.auto_reingest_enabled=True, xem
    lifespan trong src/main.py. Lỗi 1 vòng không được làm chết cả loop."""
    settings = get_settings()
    logger.info("auto_reingest: watcher started, interval=%ss", settings.auto_reingest_interval_seconds)
    while True:
        await asyncio.sleep(settings.auto_reingest_interval_seconds)
        try:
            await check_and_reingest_stale_paths()
        except Exception:
            logger.exception("auto_reingest: watcher loop iteration failed")
