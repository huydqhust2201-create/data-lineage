"""Test cho tầng observability: histogram Prometheus + JSON log.

Hai module này không phụ thuộc gì ngoài stdlib nên test được độc lập, không
cần Postgres/LLM như phần còn lại của tests/.
"""

from __future__ import annotations

import json
import logging
import sys

import pytest

from src import metrics
from src.logging_config import JsonFormatter


@pytest.fixture(autouse=True)
def _clean_metrics():
    metrics.reset()
    yield
    metrics.reset()


def _parse_samples(text: str) -> dict[str, float]:
    """Đọc output /metrics thành {dòng_metric: giá_trị}, bỏ comment."""
    samples: dict[str, float] = {}
    for line in text.strip().splitlines():
        if line.startswith("#"):
            continue
        name, _, value = line.rpartition(" ")
        samples[name] = float(value)
    return samples


# ---------- http_requests_total ----------


def test_request_counter_tach_theo_method_path_status():
    metrics.record_request("GET", "/health", 200, 1.0)
    metrics.record_request("GET", "/health", 200, 1.0)
    metrics.record_request("GET", "/health", 500, 1.0)
    metrics.record_request("POST", "/health", 200, 1.0)

    samples = _parse_samples(metrics.render_prometheus_text())
    assert samples['http_requests_total{method="GET",path="/health",status="200"}'] == 2
    assert samples['http_requests_total{method="GET",path="/health",status="500"}'] == 1
    assert samples['http_requests_total{method="POST",path="/health",status="200"}'] == 1


# ---------- histogram ----------


def test_bucket_phai_luy_tien_va_inf_bang_count():
    # 1ms, 30ms, 300ms, 7s -> rơi vào 4 bucket khác nhau
    for duration_ms in (1.0, 30.0, 300.0, 7000.0):
        metrics.record_request("GET", "/api/v1/assets", 200, duration_ms)

    samples = _parse_samples(metrics.render_prometheus_text())
    prefix = 'http_request_duration_seconds_bucket{method="GET",path="/api/v1/assets"'

    # luỹ tiến: 1ms <= 5ms nên có mặt ở mọi bucket từ 0.005 trở lên
    assert samples[prefix + ',le="0.005"}'] == 1
    assert samples[prefix + ',le="0.01"}'] == 1
    assert samples[prefix + ',le="0.05"}'] == 2  # thêm 30ms
    assert samples[prefix + ',le="0.25"}'] == 2
    assert samples[prefix + ',le="0.5"}'] == 3  # thêm 300ms
    assert samples[prefix + ',le="10"}'] == 4  # thêm 7s
    assert samples[prefix + ',le="+Inf"}'] == 4

    assert samples['http_request_duration_seconds_count{method="GET",path="/api/v1/assets"}'] == 4
    total = samples['http_request_duration_seconds_sum{method="GET",path="/api/v1/assets"}']
    assert total == pytest.approx((1.0 + 30.0 + 300.0 + 7000.0) / 1000.0)


def test_bucket_luon_khong_giam():
    for duration_ms in (0.5, 3.0, 12.0, 90.0, 400.0, 1500.0, 9000.0, 45000.0):
        metrics.record_request("GET", "/x", 200, duration_ms)

    samples = _parse_samples(metrics.render_prometheus_text())
    bucket_values = [value for name, value in samples.items() if "_bucket{" in name and 'path="/x"' in name]
    assert bucket_values == sorted(bucket_values), "bucket luỹ tiến không được giảm"


def test_duration_vuot_bucket_cuoi_chi_vao_inf():
    metrics.record_request("GET", "/slow", 200, 60_000.0)  # 60s > bucket cuối 30s

    samples = _parse_samples(metrics.render_prometheus_text())
    assert samples['http_request_duration_seconds_bucket{method="GET",path="/slow",le="30"}'] == 0
    assert samples['http_request_duration_seconds_bucket{method="GET",path="/slow",le="+Inf"}'] == 1
    assert samples['http_request_duration_seconds_count{method="GET",path="/slow"}'] == 1


def test_duration_dung_bang_bien_bucket_tinh_vao_bucket_do():
    """Ngữ nghĩa "le" là nhỏ hơn HOẶC BẰNG — 10ms phải vào bucket 0.01."""
    metrics.record_request("GET", "/edge", 200, 10.0)

    samples = _parse_samples(metrics.render_prometheus_text())
    assert samples['http_request_duration_seconds_bucket{method="GET",path="/edge",le="0.005"}'] == 0
    assert samples['http_request_duration_seconds_bucket{method="GET",path="/edge",le="0.01"}'] == 1


def test_nhan_le_khong_in_ra_dang_mot_phay_khong():
    """le="1" chứ không phải le="1.0" — Prometheus so khớp nhãn theo chuỗi."""
    metrics.record_request("GET", "/fmt", 200, 1.0)
    text = metrics.render_prometheus_text()
    assert 'le="1"' in text
    assert 'le="1.0"' not in text
    assert 'le="2.5"' in text


def test_histogram_khai_bao_dung_type():
    metrics.record_request("GET", "/t", 200, 1.0)
    text = metrics.render_prometheus_text()
    assert "# TYPE http_request_duration_seconds histogram" in text
    assert "# TYPE http_requests_total counter" in text


# ---------- llm_calls_total ----------


def test_llm_counter_theo_kind():
    metrics.record_llm_call("extraction")
    metrics.record_llm_call("chat")
    metrics.record_llm_call("chat")

    samples = _parse_samples(metrics.render_prometheus_text())
    assert samples['llm_calls_total{kind="extraction"}'] == 1
    assert samples['llm_calls_total{kind="chat"}'] == 2


# ---------- an toàn định dạng ----------


def test_escape_nhan_khong_lam_vo_payload():
    metrics.record_request("GET", '/weird"path', 200, 1.0)
    text = metrics.render_prometheus_text()
    assert '\\"' in text
    # mỗi sample vẫn phải nằm trên đúng 1 dòng, không bị ký tự lạ chẻ dòng
    assert len([line for line in text.splitlines() if line.startswith("http_requests_total{")]) == 1


def test_reset_xoa_sach():
    metrics.record_request("GET", "/health", 200, 1.0)
    metrics.record_llm_call("chat")
    metrics.reset()
    assert _parse_samples(metrics.render_prometheus_text()) == {}


def test_metrics_rong_van_render_duoc():
    """App mới khởi động, chưa có request nào — /metrics không được lỗi."""
    text = metrics.render_prometheus_text()
    assert text.endswith("\n")
    assert _parse_samples(text) == {}


# ---------- JSON log ----------


def _format(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


def _make_record(msg: str = "hello", **extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="access", level=logging.INFO, pathname=__file__, lineno=1, msg=msg, args=(), exc_info=None
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_log_ra_json_hop_le():
    """Bản cũ dùng %(message)r nên ra nháy đơn -> json.loads() nổ."""
    payload = _format(_make_record("hello"))
    assert payload["msg"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "access"
    assert "ts" in payload


def test_field_extra_duoc_day_len_cap_mot():
    payload = _format(_make_record("http_request", status=500, route="/api/v1/assets", duration_ms=12.5))
    assert payload["status"] == 500
    assert payload["route"] == "/api/v1/assets"
    assert payload["duration_ms"] == 12.5


def test_khong_ro_ri_attribute_noi_bo_cua_logrecord():
    payload = _format(_make_record("x", status=200))
    for leaked in ("pathname", "lineno", "levelno", "args", "msecs", "relativeCreated"):
        assert leaked not in payload


def test_giu_nguyen_tieng_viet():
    payload = _format(_make_record("đã ingest xong bảng khách_hàng"))
    assert payload["msg"] == "đã ingest xong bảng khách_hàng"


def test_field_khong_serialize_duoc_khong_lam_chet_log():
    class Odd:
        def __str__(self) -> str:
            return "odd-value"

    payload = _format(_make_record("x", weird=Odd()))
    assert payload["weird"] == "odd-value"


def test_exception_duoc_ghi_lai():
    try:
        raise ValueError("bum")
    except ValueError:
        record = _make_record("that bai")
        record.exc_info = sys.exc_info()
    payload = _format(record)
    assert "ValueError: bum" in payload["exc"]


def test_message_co_dau_nhay_doi_khong_pha_json():
    payload = _format(_make_record('ten bang la "orders"'))
    assert payload["msg"] == 'ten bang la "orders"'
