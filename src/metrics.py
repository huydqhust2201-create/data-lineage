"""Bộ đếm/histogram tối giản, tự viết — KHÔNG dùng prometheus-client.

Lý do giữ cách tự viết (xem thêm docs/monitoring.md): bề mặt metric cần rất
nhỏ (request count theo route+status, request duration, LLM call count) và
Prometheus text exposition format chỉ là text thuần — không cần thư viện để
sinh ra. Đổi sang prometheus-client vẫn là việc nhỏ và tách biệt nếu sau này
cần thêm multiprocess mode hoặc exemplar.

Khác bản đầu (chỉ có counter + duration_sum):
  - duration giờ là **histogram thật** (bucket + _count + _sum) nên
    Prometheus tính được p50/p95/p99 bằng histogram_quantile(). Chỉ có _sum
    như trước thì nhiều nhất chỉ ra được trung bình, không ra được percentile
    — mà trung bình thì che mất đúng cái đuôi chậm cần nhìn.
  - đơn vị đổi từ millisecond sang **second** (`http_request_duration_seconds`)
    theo đúng quy ước base-unit của Prometheus; mọi ví dụ PromQL/Grafana sẵn
    có đều giả định giây. Đổi được không mất gì vì tới giờ chưa có Prometheus
    nào từng scrape metric này, nên không có series lịch sử phải migrate.
"""

from __future__ import annotations

import threading
from bisect import bisect_left
from collections import Counter, defaultdict

# Bucket (giây) — theo bộ mặc định quen thuộc của Prometheus, nới thêm đuôi
# 30s vì endpoint chat có gọi LLM nên chậm hơn request CRUD thường nhiều.
_BUCKETS_SECONDS: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)

_lock = threading.Lock()
_request_count: Counter[tuple[str, str, int]] = Counter()
_duration_sum_seconds: defaultdict[tuple[str, str], float] = defaultdict(float)
_duration_count: Counter[tuple[str, str]] = Counter()
_duration_buckets: defaultdict[tuple[str, str], list[int]] = defaultdict(lambda: [0] * len(_BUCKETS_SECONDS))
_llm_call_count: Counter[str] = Counter()


def record_request(method: str, path: str, status: int, duration_ms: float) -> None:
    """`path` phải là **route template** (vd /api/v1/assets/{asset_id}), không
    phải URL thật — xem ghi chú cardinality trong src/main.py.

    Vẫn nhận duration theo millisecond để không phải sửa caller; quy sang giây
    ngay tại đây vì metric xuất ra theo base unit là giây.
    """
    duration_seconds = duration_ms / 1000.0
    key = (method, path)
    with _lock:
        _request_count[(method, path, status)] += 1
        _duration_sum_seconds[key] += duration_seconds
        _duration_count[key] += 1
        # bisect_left trả về bucket đầu tiên thỏa duration <= le (đúng ngữ
        # nghĩa "le" của Prometheus). Vượt bucket cuối => chỉ rơi vào +Inf,
        # mà +Inf lấy từ _duration_count nên không cần slot riêng.
        index = bisect_left(_BUCKETS_SECONDS, duration_seconds)
        if index < len(_BUCKETS_SECONDS):
            _duration_buckets[key][index] += 1


def record_llm_call(kind: str) -> None:
    """kind: vd "extraction" (llm_extraction_service) hoặc "chat" (chat_service)."""
    with _lock:
        _llm_call_count[kind] += 1


def reset() -> None:
    """Xoá toàn bộ state — chỉ dùng cho test (module giữ state ở cấp global
    nên nếu không reset thì các test sẽ phụ thuộc thứ tự chạy của nhau)."""
    with _lock:
        _request_count.clear()
        _duration_sum_seconds.clear()
        _duration_count.clear()
        _duration_buckets.clear()
        _llm_call_count.clear()


def _escape(value: str) -> str:
    """Escape label value theo Prometheus text format. Hiện `path` đã là route
    template nên gần như chắc chắn an toàn, nhưng escape vẫn rẻ và tránh việc
    một label lạ làm hỏng cả payload /metrics."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\n")


def _format_le(value: float) -> str:
    """0.005 -> "0.005", 1.0 -> "1", 2.5 -> "2.5" (tránh in ra "1.0")."""
    return f"{value:g}"


def render_prometheus_text() -> str:
    lines: list[str] = []
    with _lock:
        lines.append("# HELP http_requests_total Tổng số HTTP request đã xử lý.")
        lines.append("# TYPE http_requests_total counter")
        for (method, path, status), count in sorted(_request_count.items()):
            labels = f'method="{_escape(method)}",path="{_escape(path)}",status="{status}"'
            lines.append(f"http_requests_total{{{labels}}} {count}")

        lines.append("# HELP http_request_duration_seconds Độ trễ HTTP request (giây).")
        lines.append("# TYPE http_request_duration_seconds histogram")
        for key in sorted(_duration_count):
            method, path = key
            labels = f'method="{_escape(method)}",path="{_escape(path)}"'
            total = _duration_count[key]
            buckets = _duration_buckets[key]
            # Bucket trong Prometheus là **luỹ tiến**: le="0.01" phải gồm cả
            # phần đã đếm ở le="0.005".
            cumulative = 0
            for index, upper_bound in enumerate(_BUCKETS_SECONDS):
                cumulative += buckets[index]
                lines.append(
                    f'http_request_duration_seconds_bucket{{{labels},le="{_format_le(upper_bound)}"}} {cumulative}'
                )
            lines.append(f'http_request_duration_seconds_bucket{{{labels},le="+Inf"}} {total}')
            lines.append(f"http_request_duration_seconds_sum{{{labels}}} {_duration_sum_seconds[key]:.6f}")
            lines.append(f"http_request_duration_seconds_count{{{labels}}} {total}")

        lines.append("# HELP llm_calls_total Số lần gọi LLM, theo mục đích gọi.")
        lines.append("# TYPE llm_calls_total counter")
        for kind, count in sorted(_llm_call_count.items()):
            lines.append(f'llm_calls_total{{kind="{_escape(kind)}"}} {count}')
    return "\n".join(lines) + "\n"
