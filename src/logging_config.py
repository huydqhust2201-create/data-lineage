"""Cấu hình logging tập trung — lấp khoảng trống thật: nhiều module trong
src/ đã gọi logging.getLogger(__name__) (vd storage_service.py,
llm_extraction_service.py, chat_service.py...) nhưng chưa ai từng gọi
logging.basicConfig()/thiết lập handler, nên tới giờ các log đó chỉ rơi vào
Python's default "lastResort" handler (in ra stderr, không cấu trúc, chỉ từ
WARNING trở lên). configure_logging() gọi 1 lần lúc khởi động app, cho tất cả
logger hiện có 1 handler thật, dạng JSON 1 dòng/log để Loki/CloudWatch parse
được.

Vì sao dùng Formatter riêng thay vì format string như bản trước: bản trước
dùng `"msg":%(message)r`, mà `%r` là repr của Python nên chuỗi ra dấu nháy
ĐƠN — `{"ts":"...","msg":'{"status": 200}'}` không phải JSON hợp lệ và
json.loads() ném lỗi ngay (đã kiểm chứng). Tức là tầng log "có cấu trúc" đó
chưa từng parse được. Formatter tự build dict rồi json.dumps() mới đúng, và
thêm được field tuỳ ý qua `extra=` thành key cấp 1 (xem access log ở
src/main.py) để query theo status/route trực tiếp trong Loki.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

# Mọi attribute LogRecord chuẩn — field nào của record KHÔNG nằm trong đây
# nghĩa là do caller truyền qua extra=, và sẽ được đẩy lên JSON cấp 1.
_RESERVED_FIELDS = frozenset(vars(logging.makeLogRecord({}))) | {"asctime", "message", "taskName"}


class JsonFormatter(logging.Formatter):
    """Mỗi log record -> đúng 1 dòng JSON hợp lệ."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_FIELDS:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # ensure_ascii=False: log có tiếng Việt thì giữ nguyên chữ, không biến
        # thành \uXXXX. default=str: field lạ (Decimal, UUID, datetime...) ép
        # về str chứ không cho TypeError làm chết luôn câu lệnh log.
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    # Gỡ handler cũ (tương đương force=True của basicConfig) để gọi 2 lần
    # không in log ra 2 lần.
    for existing in root.handlers[:]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)
