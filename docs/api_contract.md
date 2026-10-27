# API Contract — DATA-04 Data Lineage Agent

> Toàn bộ request/response dùng schema Pydantic thật trong `src/models/schemas.py` — không phải giả định. Khi backend implement khác đi so với file này, **sửa file này trước, báo cả team, rồi mới đổi code**.

Base path: `/api/v1` (xem `src/main.py`)

## POST /api/v1/ingest

Bắt đầu 1 lượt phân tích (FR-1..FR-5). Đây là bước đầu tiên, bắt buộc trước khi có gì để query.

**Request** (`IngestRequest`):
```json
{
  "input_path": "samples/jaffle-shop",
  "dialect": null
}
```

**Response** (`IngestResponse`):
```json
{
  "sql_files_found": 13,
  "parsed_count": 10,
  "unparsed_count": 3,
  "pending_review_count": 3,
  "overview_graph": {
    "nodes": [{ "id": "raw_customers", "label": "raw_customers" }, { "id": "stg_customers", "label": "stg_customers" }],
    "confirmed_edges": [ /* list LineageEdge đã ghi thẳng vào graph — parser hoặc LLM confidence cao */ ],
    "pending_edges": [ /* list LineageEdge — CHỈ những edge_id trong đây gọi được /pending-review/{id}/confirm|reject */ ]
  }
}
```

`overview_graph` là đồ thị table-level của **các bảng vừa phát hiện trong lượt ingest này** (không phải toàn bộ đồ thị tích luỹ trong Postgres — muốn cái đó thì gọi `GET /graph`). Mục đích: client vẽ ngay bức tranh tổng sau khi ingest, không cần chờ user submit 1 impact query trước.

⚠️ **`confirmed_edges` và `pending_edges` tách riêng có chủ đích, đừng gộp lại khi code FE** — bug thật đã xảy ra khi test tay: lấy nhầm `edge_id` từ 1 cạnh trong `confirmed_edges` rồi gọi `/pending-review/{id}/confirm` → 404, vì cạnh đó chưa từng vào hàng đợi pending (chỉ cạnh trong `pending_edges` mới confirm/reject được).

`pending_review_count > 0` → nên điều hướng user sang màn hình HITL Review.

⚠️ **Nhiều lần gọi `/ingest`/`/ingest/upload` riêng biệt sẽ CỘNG DỒN vào cùng 1 đồ thị lineage** (không tự xoá dữ liệu của lượt trước) — đúng theo thiết kế, vì lineage 1 dự án thật thường được ingest rải rác qua nhiều lần/nhiều file. Muốn bắt đầu lại từ đầu (demo/test), gọi `DELETE /graph` trước.

## POST /api/v1/ingest/upload

Giống hệt `/ingest` về logic (cùng gọi `_run_ingest()` dùng chung, cùng response `IngestResponse`), nhưng nhận file **tải trực tiếp từ máy client** thay vì 1 path có sẵn trên server — dùng khi FE cho user chọn thư mục local (input `webkitdirectory`) thay vì gõ đường dẫn server.

**Request:** `multipart/form-data`, field `files` lặp lại nhiều lần (1 file 1 phần). Set `filename` = đường dẫn tương đối (`file.webkitRelativePath`, vd `"models/staging/stg_customers.sql"`) để giữ cấu trúc thư mục — server ghi ra thư mục tạm theo đúng cấu trúc đó trước khi chạy pipeline, nên `evidence.file_path` trong response vẫn có ý nghĩa.

**Response:** `IngestResponse`, y hệt `/ingest`.

**Lỗi:**
- `400` nếu không có file `.sql` nào trong danh sách (file khác đuôi bị lọc bỏ âm thầm, không báo lỗi riêng từng file)
- `400` nếu tên file cố thoát khỏi thư mục tạm (`../`, path tuyệt đối) — bị chặn ở `_safe_relative_path()`, không phải lỗi cần FE xử lý đặc biệt, chỉ cần biết response có thể là 400

File tạm bị xoá ngay sau khi request xử lý xong (`tempfile.TemporaryDirectory`), không lưu lại trên server.

## GET /api/v1/pending-review

Danh sách cạnh đang chờ xác nhận (confidence < `confidence_threshold`, FR-4).

**Response:** `list[LineageEdge]`
```json
[
  {
    "edge_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "source_table": "raw.orders",
    "source_column": null,
    "target_table": "customer_ltv",
    "target_column": null,
    "transform_type": "unknown",
    "confidence": 0.55,
    "source_type": "llm",
    "evidence": {
      "file_path": "scripts/legacy_ltv_calc.sql",
      "line_range": null,
      "raw_sql": "... nguyên văn nội dung file ...",
      "reasoning": "Dynamic SQL nối chuỗi qua Jinja macro chưa compile được bằng parser",
      "fallback_reason": "sqlglot parse error: unresolved macro `calc_ltv_expr()`"
    }
  }
]
```

`evidence` luôn có ở cạnh LLM (`reasoning` + `fallback_reason` không rỗng). Cạnh parser cũng có `evidence` nhưng chỉ `file_path`/`raw_sql`/`line_range` (không có `reasoning`/`fallback_reason`, vì không qua LLM). `line_range` là **xấp xỉ** (tìm dòng chứa tên cột/bảng trong file gốc), không phải vị trí AST chính xác — sqlglot không track vị trí nguồn theo mặc định.

## POST /api/v1/pending-review/{edge_id}/confirm

Xác nhận 1 cạnh → ghi chính thức vào graph + persist (FR-4, FR-5). Không có request body. Response: `LineageEdge` đã confirm. Sau lệnh này, cạnh biến mất khỏi `inferred_pending` và xuất hiện trong `confirmed` ở lần `GET /impact` tiếp theo — **không cần re-ingest**.

## POST /api/v1/pending-review/{edge_id}/reject

Từ chối 1 cạnh → loại bỏ, không ghi vào graph. Không có request body. Response: `204 No Content`.

## GET /api/v1/impact/{table}

Impact analysis 2 chiều (US-5, US-6, FR-6), **tách rõ 2 khối không bao giờ gộp** (US-3, US-4):
- `confirmed` — cạnh parser (confidence=1.0) hoặc cạnh LLM đã qua HITL confirm. Agent "khẳng định chắc chắn".
- `inferred_pending` — cạnh LLM confidence thấp, **chưa** qua HITL. Agent "nghi ngờ, cần xác nhận thêm" — luôn kèm evidence, không bao giờ ẩn.

**Query params:** `column` (optional), `direction` = `downstream` | `upstream` (bắt buộc)

Ví dụ: `GET /api/v1/impact/orders?column=total_amount&direction=downstream`

**Response** (`ImpactQueryResult`):
```json
{
  "table": "orders",
  "column": "total_amount",
  "direction": "downstream",
  "confirmed": [
    {
      "source": { "table": "orders", "column": "total_amount" },
      "target": { "table": "daily_revenue", "column": "revenue" },
      "source_type": "parser",
      "confidence": 1.0,
      "hitl_status": "confirmed",
      "evidence": {
        "file_path": "models/marts/daily_revenue.sql",
        "line_range": [12, 12],
        "raw_sql": "... nguyên văn file ...",
        "reasoning": null,
        "fallback_reason": null
      }
    }
  ],
  "inferred_pending": [
    {
      "source": { "table": "orders", "column": null },
      "target": { "table": "customer_ltv", "column": null },
      "source_type": "llm",
      "confidence": 0.62,
      "hitl_status": "pending",
      "evidence": {
        "file_path": "scripts/legacy_ltv_calc.sql",
        "line_range": null,
        "raw_sql": "...",
        "reasoning": "Dynamic SQL build string tại dòng ~40 nối total_amount vào biểu thức LTV",
        "fallback_reason": "sqlglot parse error: unresolved macro `calc_ltv_expr()`"
      }
    }
  ]
}
```

Lưu ý shape khác `LineageEdge` phẳng: `source`/`target` lồng nhau (`{table, column}`) thay vì `source_table`/`source_column` — chỉ áp dụng cho response endpoint này, không đổi `LineageEdge` gốc dùng nội bộ (graph storage, pending-review...).

`inferred_pending` gồm cả cạnh bám thẳng vào `table`/`column` được hỏi (hop đầu) lẫn cạnh nối tiếp từ 1 bảng đã có trong `confirmed` (hop sau) — để thấy "giả thuyết tiếp theo", không chỉ 1-hop từ gốc.

## GET /api/v1/graph

Toàn bộ đồ thị **đã xác nhận, tích luỹ từ trước tới nay** trong Postgres (khác `overview_graph` của `/ingest` — cái đó chỉ show lượt vừa rồi).

**Response** (`GraphResponse`):
```json
{
  "nodes": [
    { "id": "raw.orders", "label": "raw.orders" },
    { "id": "stg_orders", "label": "stg_orders" }
  ],
  "edges": [ /* list LineageEdge đầy đủ evidence, giống format ở trên */ ]
}
```

Dùng `edge.source_type` để style nét liền (parser) vs nét đứt (llm) nếu vẽ đồ thị.

## DELETE /api/v1/graph

Xoá toàn bộ đồ thị lineage đã tích luỹ (kể cả trên Postgres) + hàng đợi HITL đang chờ duyệt. Trả `204 No Content`.

Nhiều lần gọi `/ingest`/`/ingest/upload` riêng biệt **cộng dồn** thành 1 đồ thị lineage toàn dự án theo thiết kế (không tự xoá giữa các lần) — endpoint này là lối thoát thủ công khi người dùng chủ động muốn bắt đầu lại từ đầu (vd chuyển sang test/demo với bộ dữ liệu khác).

## POST /api/v1/chat

Hỏi lineage bằng ngôn ngữ tự nhiên. Gửi lại `session_id` từ response trước để tiếp tục làm rõ tên bảng.

**Request:**
```json
{"question": "sửa orders thì ảnh hưởng gì", "session_id": null}
```

**Response:** `ChatResponse` gồm văn xuôi `answer`, fact có cấu trúc tách biệt trong `confirmed`/`inferred_pending`, `steps` là dấu vết tool, `clarification_options` và `suggestions` là hành động client cần mời user thực hiện. Không có `status`, `intent`, `direction`, `resolved_table`, `paths` hay các scalar tổng hợp theo một tool đầu tiên.

Mỗi `ChatStep` giữ cặp dữ kiện đầy đủ: `args` là tên agent đã gọi (chưa resolve), `resolved` là bảng/cột/chiều đã chốt nếu thành công, và `error` là lỗi của chính step nếu có. Client đọc bảng đã chốt, chiều truy vấn hoặc lỗi từ step tương ứng, không đọc từ field response cấp cao.

Ví dụ làm rõ hai lượt:
```json
{"session_id":"abc","answer":"Chọn một bảng.","confirmed":[],"inferred_pending":[],"clarification_options":["ecom.orders","stg.orders"],"suggestions":[],"warnings":[],"steps":[{"tool":"downstream","args":{"table":"orders"},"resolved":null,"error":"ambiguous","summary":"ambiguous"}]}
```
```json
{"question":"2","session_id":"abc"}
```
```json
{"session_id":"abc","answer":"...","confirmed":[],"inferred_pending":[],"clarification_options":[],"suggestions":[],"warnings":[],"steps":[{"tool":"downstream","args":{"table":"stg.orders"},"resolved":{"table":"stg.orders","column":null,"direction":"downstream"},"error":null,"summary":"0 confirmed, 0 pending"}]}
```

`steps` luôn là mảng (có thể rỗng):
```json
[{"tool":"downstream","args":{"table":"stg.orders"},"resolved":{"table":"stg.orders","column":null,"direction":"downstream"},"error":null,"summary":"1 confirmed, 0 pending"}]
```

Ví dụ câu hỏi quan hệ hai bảng đang hoãn ở phase này:
```json
{"answer":"...","clarification_options":[],"suggestions":[],"steps":[]}
```

Khi `clarification_options` không rỗng, gửi lại số thứ tự hoặc tên ứng viên cùng `session_id` để chatbot chạy tiếp câu hỏi gốc. Khi `suggestions` không rỗng, client có thể mời user thử lại một tên gần đúng. Nếu `session_id` trong response khác giá trị client gửi, session cũ đã hết hạn, bị evict, hoặc backend vừa restart; client phải coi ngữ cảnh đã mất.

`review_service` và chat session store đều in-memory, vì vậy backend phải chạy một process. Không dùng nhiều worker/container cho đến khi cả hai state store được chuyển sang shared storage.

## GET /health, GET /api/v1/status

Dùng để healthcheck (Docker) và kiểm tra agent sẵn sàng chưa.

## Trạng thái

Đã implement thật trong `src/api/routes.py`, gồm `/chat`, `confirmed`/`inferred_pending`, `steps`, `overview_graph` và `evidence`.
