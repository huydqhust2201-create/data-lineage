# Worklog — Team [Tên Team]

> Ghi lại tất cả công việc đã làm theo ngày. Ai làm gì, kết quả gì.

---

## 2026-07-25

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Huy DQ | Setup môi trường dev (venv, `pip install -r requirements.txt`) | ✅ Done | `.venv` tạo bằng Python 3.14.5 | 0.5h |
| Huy DQ | Tạo `.env` từ `.env.example` | ✅ Done | Cần điền `OPENAI_API_KEY`, `AI_LOG_API_KEY` riêng của team | 0.2h |
| Huy DQ | Cài AI Logging pre-push hook (`scripts/setup_hooks.ps1`) | ✅ Done | `.git/hooks/pre-push` đã cài | 0.2h |

**Tổng kết ngày:** Hoàn tất setup ban đầu của repo (môi trường + AI logging hooks); còn thiếu API keys thật trước khi chạy server.

---

## 2026-08-11

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Công | Phân tích Olist, viết test 08, cấu hình DBT model, push code lên feature/sql-parser | ✅ Done | Push nhánh feature/sql-parser thành công | 1.5h |

**Tổng kết ngày:** Đã tích hợp thành công bộ nguồn phân tích Olist phức tạp, cấu hình DBT model sử dụng Jinja ref, viết test case 08 và kiểm thử API hoàn tất (tất cả 87 tests đều pass). Fix lỗi git hook và push nhánh feature/sql-parser thành công.

---

## 2026-08-15

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Công | Thực hiện cải tiến 3.1-3.6 cho Pipeline 1: Lazy loading parser, chống nhân đôi cạnh, song song trích xuất LLM, DAG Cycle detection, error reporting & caching | ✅ Done | - Cập nhật `llm_extraction_service.py`, `graph_service.py`, `parser_service.py`, `lineage_nodes.py`, `state.py`<br>- Viết test suite `test_pipeline_improvements.py`<br>- Đạt 100% test passed (194 tests)<br>- Tạo file `tests_evaluation_report.md` | 2.5h |

**Tổng kết ngày:** Đã hoàn thành toàn bộ cải tiến 3.1–3.6 của Pipeline 1 đúng yêu cầu, xử lý triệt để side-effects, cải thiện tốc độ xử lý của pipeline (từ ~28s xuống còn ~16s thông qua song song hóa ThreadPool và cache ở Parser), chống trùng lặp cạnh và phát hiện chu trình DAG, hoàn thành bộ test đạt 100% pass rate.

---

## 2026-08-31

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Hoàng | Column type + constraint cho Impact Analysis (bản A — đọc DDL nguồn) | ✅ Done | - `ColumnSchema` model; parser `_extract_column_schema()` đọc `CREATE TABLE (col TYPE constraint...)`<br>- bảng RIÊNG `lineage_column_schema` (không đụng `lineage_nodes`)<br>- `/graph` trả `column_schemas`, FE hết hard-code `type:"unknown"`, badge PK/FK/NN<br>- Tier 2: lan `data_type` qua cạnh `direct`<br>- Impact `schema_change_note()` hướng sự thật + `_type_transition_verdict` (mở rộng/thu hẹp/đổi họ kiểu)<br>- sample `samples/hospital/sources/raw_schema.sql`<br>- **Doc: `docs/impact_column_schema.md`** | |
| Hoàng | Fix bug cạnh nhân bản mỗi lần re-ingest (risk note lặp trên UI) | ✅ Done | - `storage_service` không round-trip `dependency_kind` → cạnh control nhân bản. Thêm cột `dependency_kind` + `load()` dedup<br>- re-ingest `samples/hospital` 4× → 82 cạnh không đổi (trước +26/lần)<br>- dọn tay cruft ở db `default` + `New Workspace` | |
| Hoàng | Gom Impact Analysis theo QUAN HỆ bảng + làm gọn code chấm rủi ro | ✅ Done | - 1 card / quan hệ (`A→B`), câu dẫn schema 1 lần, mỗi vai trò 1 dòng (chip đen)<br>- bỏ `assert` ép điền đủ 8 change_kind → ô trống rơi về fallback an toàn<br>- `schema_change_note` 6 nhánh verdict → 2 nhánh; ghi chú PHẠM VI đông cứng bảng luật | |

**Tổng kết ngày:** Hoàn thành tính năng column type + constraint (bản A) cho Impact Analysis
end-to-end trên nhánh `feat/column-schema-and-constraint-impact` (8 commit `3ca76fc`..`d886f70`,
+1620/-61, 25 file). Trong lúc verify phát hiện + sửa 1 bug có sẵn (từ đợt control lineage):
`dependency_kind` không được persist khiến cạnh control nhân bản mỗi lần re-ingest → Impact
Analysis hiện risk note lặp. Gộp thêm 1 đợt refactor chống code chấm rủi ro phình combinatorial
theo phản hồi BTC. Gate: `pytest` 678 passed/0 failed, `ruff` + FE `typecheck`/`build`/`vitest`
sạch. Chi tiết kỹ thuật + cách verify: `docs/impact_column_schema.md`. **Chưa PR.**

---

## [YYYY-MM-DD]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| | | | | |

**Tổng kết ngày:**

---

<!-- Format: copy block trên cho mỗi ngày làm việc -->
