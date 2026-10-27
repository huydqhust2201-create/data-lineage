# Ground Truth — bộ dữ liệu đối chiếu cho parser_service

> Owner: Nguyễn Thành Công. Dùng để đo precision/recall của `parser_service.py` (PRD.md mục 3).

## Cách thêm 1 case mới

1. Thêm file `.sql` vào `sql/` (đặt tên mô tả case, vd `join_two_tables.sql`, `dynamic_jinja.sql`)
2. Thêm file `.json` cùng tên vào `expected/` — danh sách `LineageEdge` đúng mà bạn tự xác định bằng mắt
3. Test trong `tests/test_services/test_parser_service.py` sẽ đọc cặp file này, chạy `parser_service.parse_file()`, so khớp với expected

## Format file expected (`expected/<tên>.json`)

```json
[
  {
    "source_table": "raw.orders",
    "source_column": null,
    "target_table": "stg_orders",
    "target_column": null,
    "transform_type": "direct",
    "confidence": 1.0,
    "source_type": "parser"
  }
]
```

## Loại case nên cover (ưu tiên theo PRD mục 10 — risk "chưa có dữ liệu thật")

- [x] SELECT đơn giản (1 bảng nguồn → 1 bảng đích)
- [x] JOIN nhiều bảng
- [x] CTE (WITH ... AS)
- [x] Aggregation (GROUP BY, SUM/COUNT...)
- [x] Window function
- [x] Case parser **phải fail** (dynamic SQL ghép chuỗi, Jinja macro dbt chưa compile) — dùng để test nhánh LLM fallback, không phải test parser đúng

## ⚠️ Bẫy khi thêm case "cố ý fail" vào file nhiều statement

`_parse_core_events()` gọi `sqlglot.parse()` trên **toàn bộ nội dung file trong 1 lần** — không có cơ chế cô lập lỗi theo từng statement. Nếu 1 statement trong file bị lỗi cú pháp (SQL động ghép chuỗi, Jinja chưa compile...), **CẢ FILE mất trắng lineage**, kể cả các statement hợp lệ khác đứng trước nó trong cùng file (đã tự kiểm chứng khi build case 13 — ghép chung 1 file 700+ dòng hợp lệ với 2 statement cố ý lỗi ở cuối → 0 cạnh cho toàn bộ file).

→ **Case "phải fail" luôn phải nằm ở file `.sql` riêng, tách biệt hoàn toàn khỏi các case hợp lệ** — xem `07_dynamic_sql_fail.sql` (đã theo đúng quy tắc này từ đầu) và `samples/complex_pipeline/dynamic_sql_and_jinja_placeholder.sql` (case lớn hơn, thêm gần đây).

## ⚠️ "Fail parser tĩnh" KHÔNG đồng nghĩa "vào được hàng đợi HITL"

Case cố ý fail có 2 kiểu kết cục rất khác nhau ở bước LLM fallback (đã tự kiểm chứng bằng `llm_extraction_service.extract_edges_from_files()` thật, không đoán):

- **Bế tắc hoàn toàn** (tên bảng/điều kiện phụ thuộc 100% biến runtime, hoặc Jinja lồng quá phức tạp) → LLM trả về `unresolved` với **đúng 0 cạnh** — không có gì để vào HITL. Đây là hành vi ĐÚNG theo thiết kế (`Prefer unresolved over guessing` trong prompt), không phải bug. Ví dụ: `dynamic_sql_and_jinja_placeholder.sql`.
- **Fail parser tĩnh nhưng tên bảng vẫn là literal tĩnh trong chuỗi SQL động** (chỉ điều kiện lọc phụ thuộc biến) → LLM trích được cạnh thật với `confidence < 1.0`, `source_type="llm"` — cạnh này MỚI thực sự hiện "LLM Generated" (cam) trên Lineage Explorer và vào `GET /pending-review` (HITL Queue). Ví dụ: `llm_fallback_demo.sql`.

Muốn test riêng luồng HITL, ingest `llm_fallback_demo.sql` — không dùng `dynamic_sql_and_jinja_placeholder.sql` (case đó chủ đích test nhánh "LLM cũng bó tay", không sinh cạnh).

## Case lớn/phức tạp

- `13_saas_analytics_pipeline.sql` + `expected/13_saas_analytics_pipeline.json` — case gắn pytest, 9 statement CREATE TABLE/VIEW AS chuỗi 4 lớp (staging → intermediate → mart → reporting), CTE lồng 3 tầng, window function, CASE WHEN lồng, UNION ALL, subquery tương quan. `expected` chỉ liệt kê 1 tập con đại diện đã chạy `parser_service.parse_file()` thật để xác minh (test chỉ đòi hỏi expected ⊆ actual, không cần liệt kê hết — xem `test_ground_truth_parser_precision_chinook_sakila` trong `test_parser_service.py`).
- `samples/complex_pipeline/` — bản LỚN hơn, KHÔNG gắn pytest, dùng để test thủ công qua app thật (`POST /ingest`, Lineage Explorer, Impact Analysis, Chat Copilot, HITL Queue). Cùng miền dữ liệu SaaS/e-commerce, ingest cả thư mục để thấy đủ 3 trạng thái cùng lúc:
  - `warehouse_pipeline.sql` (703 dòng, 28 statement, 294 cạnh) — "Verified Flow" (xanh), multi-hop 5 tầng, recursive CTE, self-join.
  - `dynamic_sql_and_jinja_placeholder.sql` — bế tắc hoàn toàn, 0 cạnh, không vào HITL.
  - `llm_fallback_demo.sql` — 2 cạnh "LLM Generated" (cam) confidence 0.4, vào HITL Queue thật.

Cách tạo 1 case mới cần chạy parser thật để lấy expected JSON (đừng đoán bằng mắt — parser có vài heuristic không hiển nhiên, vd với bare `SELECT` nhiều CTE không `CREATE TABLE`, `target_table` suy ra từ alias đầu tiên trong `FROM` của SELECT cuối chứ không phải tên CTE cuối cùng được định nghĩa):

```bash
python -c "
from src.services.parser_service import SQLParserService
svc = SQLParserService(default_dialect='postgres')
edges = svc.parse_file('tests/ground_truth/sql/<file>.sql')
for e in edges: print(e.source_table, e.source_column, '->', e.target_table, e.target_column, e.transform_type)
"
```
