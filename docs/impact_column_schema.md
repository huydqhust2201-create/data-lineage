# Column type + constraint cho Impact Analysis

> Nhánh `feat/column-schema-and-constraint-impact` (từ `main` @ `6d017a6`).
> 10 commit, `3ca76fc`..`dc29eab`. Chưa PR.
> Trạng thái: **xong**, đã verify trên `samples/hospital`.

---

## 1. Vấn đề

Trên UI (Data Catalog + Impact Analysis), **mọi cột đều không có kiểu dữ liệu và
không có constraint**. Nguyên nhân: toàn bộ pipeline chưa mô hình hoá type/constraint —
parser gặp `CREATE TABLE` chỉ lấy tên bảng rồi vứt danh sách cột; `GraphNode.columns`
chỉ có mô tả; adapter frontend hard-code `type: "unknown"`.

Impact Analysis với `change_kind = type` / `constraint` vì thế chỉ trả text tĩnh
chung chung — không biết cột đang đổi vốn là kiểu gì, đã NOT NULL hay chưa, có phải
khoá không.

## 2. Quyết định phạm vi

Sản phẩm lớn (DataHub, OpenMetadata, dbt Cloud) lấy type/constraint từ **system catalog
của warehouse** qua connector. Dự án ta phân tích tĩnh repo, không có connector → nguồn
tự động đó ngoài phạm vi.

| Phương án | Quyết định |
|---|---|
| **Bản A** — chỉ đọc cái đã KHAI BÁO (`CREATE TABLE x (col TYPE constraint...)` trong file ingest) | ✅ **Làm** |
| **Bản B** — suy luận kiểu cho cột dẫn xuất qua CAST/aggregate/CASE | ❌ **Loại** — quá rộng, hiện sai kiểu với vẻ chắc chắn còn tệ hơn để trống |

Giới hạn cố hữu của bản A: DDL chỉ tồn tại cho bảng **raw/source** (dbt model là
`SELECT`, `CREATE TABLE AS SELECT` không mang danh sách cột) → **type chỉ sống ở tầng raw**.
Constraint giải quyết nhóm rủi ro ràng buộc nguồn → đích.

## 3. Kiến trúc

```
CREATE TABLE raw_x (id INT NOT NULL PRIMARY KEY, ...)   ← file .sql trong repo
        │  parser_service._extract_column_schema()
        ▼
GraphEvent(kind="declare", columns=[ColumnSchema(...)])
        │  graph_build_node
        ▼
bảng RIÊNG  lineage_column_schema  (khoá: database_id, table_name, column_name)
        │                              ↑ KHÔNG đụng lineage_nodes
        ▼
GET /graph      →  GraphNode.column_schemas   →  FE badge PK/FK/NN, kiểu
GET /impact     →  impact_service.schema_change_note()  →  câu "sự thật" dẫn đầu risk
```

### Tier 1 — declared (từ DDL)

- **`src/models/schemas.py`**: `ColumnSchema { name, data_type, is_nullable, is_primary_key,
  is_foreign_key, references_table, references_column, origin }`. Thêm `GraphEvent.columns`,
  `GraphNode.column_schemas`.
- **`src/services/parser_service.py`**: `_extract_column_schema()` + `_parse_reference()` —
  đọc `exp.ColumnDef.kind` (kiểu) + `.constraints` (`NotNullColumnConstraint`,
  `PrimaryKeyColumnConstraint`, `Reference`, `UniqueColumnConstraint`) + PK/FK mức bảng.
  Wire vào nhánh `exp.Create`. `CREATE TABLE AS SELECT` (không có `exp.Schema`) → `[]`,
  đường đi cũ nguyên vẹn.
- **`src/services/storage_service.py`**: bảng `lineage_column_schema` (auto-create trong
  `_connect()`). `replace_column_schema` / `load_column_schema_by_names` /
  `rename_column_schema_table` / `drop_column_schema_table`.
- **`src/agents/nodes/lineage_nodes.py`** (`graph_build_node`): gom `declared_columns` từ
  event declare, persist vô điều kiện sau `upsert_nodes`; rename/drop bảng → schema đi theo.
- **`src/api/routes.py`**: `/graph` trả `column_schemas`; `/impact/{table}` thêm param `target_type`.
- **Frontend**: `backend.ts` (`ColumnSchemaView`), `backendToLineage.ts` (bỏ hard-code
  `"unknown"`, map PK/FK/NN), `DataCatalogView.tsx` (badge FK/NN, `~` cho propagated),
  `ImpactAnalysisView.tsx` (ô nhập "Kiểu dữ liệu đích").
- **Sample**: `samples/hospital/sources/raw_schema.sql` — 8 bảng raw đầy đủ type + PK/FK/NOT NULL.

### Tier 2 — propagated (qua cạnh `direct`)

`_propagate_column_schema()` trong `lineage_nodes.py`: lan **CHỈ `data_type`** qua cạnh
parser `transform_type="direct"` (truyền cột nguyên trạng qua SELECT), theo thứ tự topo,
bỏ qua nếu đồ thị có chu trình.

**KHÔNG lan**:
- PK/FK — khoá không "chảy" qua SELECT.
- `is_nullable` — 1 cột NOT NULL đi qua LEFT JOIN thành nullable, mà hàm không nhìn thấy
  loại JOIN từ đồ thị. Cột propagated luôn `is_nullable=True` = "chưa xác định".

Cột propagated gắn cờ `origin="propagated"` → UI hiển thị `~kiểu`, impact hạ mức tin cậy
("kiểu suy diễn, chưa có DDL — cần xác minh").

### Impact schema-aware — hướng SỰ THẬT

`schema_change_note()`:
- `_describe_column()` — liệt kê SỰ THẬT: `Cột \`x\`: kiểu \`INT\`, PRIMARY KEY (ngầm NOT NULL).`
  KHÔNG phán mức rủi ro (người đọc tự suy: PK ⇒ thêm NOT NULL là no-op).
- Chỉ thêm 1 **hệ quả** khi TÍNH ĐƯỢC điều cụ thể:
  - đổi kiểu + có `target_type` → `_type_transition_verdict()` (mở rộng / thu hẹp / đổi họ kiểu)
  - thêm constraint vào cột đang nullable → "cần backfill" + đếm model downstream JOIN
- Không có schema → note tĩnh cũ y nguyên.

## 4. Bug phát hiện khi verify (KHÔNG phải của feature này)

### 4.1. Cạnh nhân bản mỗi lần re-ingest → risk note lặp trên UI (`5ff73c0`)

`storage_service.save()`/`load()` **không round-trip `dependency_kind`**. Sau save→load
mọi cạnh control (`join_key`/`group_key`/`filter`/`window_*`) đọc lại thành `"output"` →
`graph_service.add_edge` dedup theo `(source_column, target_column, source_type,
dependency_kind)` không match được → **mỗi lần re-ingest thêm 1 bản**. Impact Analysis
hiện 4-7 dòng risk note y hệt cho cùng 1 cặp bảng.

Bug có sẵn từ đợt thêm control lineage (PR #103), bị khuếch đại do test ingest nhiều lần.

**Fix**: `lineage_edges` thêm cột `dependency_kind` (`ALTER ... ADD COLUMN IF NOT EXISTS`);
`load()` gộp cạnh trùng theo đúng contract `add_edge`, giữ confidence cao nhất → DB cũ
tự lành ở lần load kế. Verify: re-ingest `samples/hospital` 4× → 82 cạnh không đổi
(trước: +26/lần).

**Dọn tay** (SQL, db `default` + `New Workspace`): xoá cạnh cruft `source_column IS NOT NULL
AND target_column IS NULL AND dependency_kind='output' AND transform_type='unknown'` — cạnh
control mất nhãn từ trước fix. Lưu ý: re-ingest KHÔNG tự gỡ cạnh stale (chỉ thêm) — hạn chế
cố hữu, ngoài phạm vi.

### 4.2. Gom hiển thị theo QUAN HỆ (`290aef1`, `3c952eb`)

1 cặp bảng có nhiều cạnh THẬT khác nhau (cột chảy vào output + CÙNG cột đó làm khoá JOIN +
GROUP BY) → UI cũ render mỗi cạnh 1 card. Giờ **1 card / quan hệ** (`A → B`), câu dẫn schema
hiện 1 lần, mỗi vai trò 1 dòng (chip `<code>` nền đen: `patient_id → patient_id` / role
badge KHOÁ JOIN / GROUP BY) + rủi ro riêng.

`ImpactEdgeView.schema_note` (mới) tách câu dẫn schema ra để FE hiện 1 lần cho cả nhóm;
`risk` giữ chuỗi đầy đủ (không phá CSV export / chat).

## 5. Làm gọn code chấm rủi ro (`d886f70`)

Phản hồi: mỗi trường hợp mới lại kéo theo "mở rộng", code phình dần
(`transform_type × change_kind × dependency_kind`), `assert` lúc import ép điền mọi ô.

- **Bỏ `assert` phủ-đủ-8-change_kind.** `risk_note()` ô trống → `_RISK_FALLBACK` ("cần đánh
  giá thủ công"). Thêm `change_kind`/`dependency_kind` mới KHÔNG còn bắt buộc điền lại bảng.
- **`schema_change_note`: 6 nhánh verdict → 2 nhánh consequence.** Hướng sự thật.
- Ghi chú **PHẠM VI** cuối `impact_service.py`: 2 bảng luật `_RISK_BY_TRANSFORM` /
  `_RISK_BY_DEPENDENCY` **đông cứng** — trường hợp mới ưu tiên (a) nhóm thô có sẵn,
  (b) fallback, (c) chỉ code riêng khi có user thật vướng.

Nội dung 2 bảng luật GIỮ NGUYÊN (đã test).

## 6. Đã verify (2026-08-31)

- **UI thật** (Chrome): Data Catalog `raw_patients`/`raw_invoices` hiện đúng type + icon PK
  + badge FK + badge NN khớp `raw_schema.sql`. Impact Analysis: card gom theo quan hệ,
  chip `<code>` nền đen tách định danh khỏi giải thích, câu dẫn schema 1 lần/card, verdict
  "THU HẸP" hiện đúng, ô "Kiểu dữ liệu đích" bật khi chọn "Sửa kiểu dữ liệu".
- **rename/drop bảng qua agent thật** (`build_graph().ainvoke`): 2 test end-to-end. Quá trình
  này phát hiện + fix 1 bug: `DROP TABLE` không xoá `column_schema` (`declared_columns` không
  được pop → `replace_column_schema` re-insert lại).
- **Dialect** (BigQuery/Snowflake/MySQL/T-SQL): sqlglot chuẩn hoá về kiểu canonical
  (`INT64→BIGINT`, `STRING→TEXT`, `NUMBER→DECIMAL`, `NVARCHAR→VARCHAR`), PK/NN/FK
  detect độc lập dialect. Kiểu lạ (`UINT`...) rơi về "cần kiểm tra thủ công" an toàn.
- **Sample khác** (jaffle-shop/olist/chinook): ingest bình thường, `column_schemas` rỗng
  (không có DDL nguồn), edge count không đổi.

## 7. Giới hạn còn lại (chấp nhận)

- Type chỉ có ở raw (declared) + cột truyền thẳng (propagated `data_type` only).
  Cột qua aggregate/CASE/join vẫn trống type.
- Verdict rủi ro là **lời khuyên cho người sẽ tự kiểm tra**, không phải phán quyết
  (vd "BIGINT→INT rủi ro CAO" đúng *nếu* dữ liệu vượt 2³¹ — ta không có dữ liệu).
- Chat path (`impact_tools.py`) chưa schema-aware — vẫn dùng `risk_note` 3 tham số, chạy bình thường.
- `catalog.json` / `schema.yml` reader: hoãn.
- Sample khác (olist/chinook/...) chưa có DDL nguồn → catalog view của chúng vẫn trống.
- Re-ingest không gỡ cạnh stale (chỉ thêm, không xoá cạnh mà lần parse hiện tại không sinh ra).

## 8. Test

| File | Số case | Nội dung |
|---|---|---|
| `tests/test_services/test_parser_service.py` | +3 | parse DDL → ColumnSchema (type, PK/FK cột + bảng, CREATE AS SELECT → rỗng) |
| `tests/test_services/test_impact_schema_aware.py` | 15 | `_type_transition_verdict`, `schema_change_note` facts-forward, fallback ô trống |
| `tests/test_agents/test_propagate_column_schema.py` | 9 | Tier 2: happy path, multi-hop, cycle→`{}`, không mang PK/FK, LEFT-JOIN safety... |
| `tests/test_services/test_column_schema_storage.py` | 12 | storage (replace/load/rename/drop/propagated) + `dependency_kind` round-trip + **2 end-to-end**: rename/drop bảng qua `build_graph().ainvoke`. Chạy trên **DB throwaway riêng** → KHÔNG bị gate `PYTEST_ALLOW_DB_WIPE` |
| `tests/test_services/test_impact_control_lineage.py` | sửa | rename test cho khớp hành vi mới |
| `tests/test_agents/test_graph.py`, `test_pipeline_improvements.py`, `test_api/test_routes.py` | sửa | `fake_storage` stub thêm hàm storage mới; fix assert `test_re_ingest_same_folder_no_duplicate` (trước không assert gì) |
| `frontend/src/adapters/backendToLineage.test.ts` | 3 | adapter map `column_schemas` → `ColumnDef` |
| `frontend/src/utils/impactGrouping.test.ts` | 7 | `stripSchemaNote` / `roleRank` / `ROLE_LABEL` |

**Gate:** `pytest tests/` **680 passed / 0 failed**; `ruff check src/ tests/` sạch;
`npm run typecheck` + `build` + `vitest` (30) sạch. UI verify thật trên Chrome (mục 6).

## 9. Cách verify tay

```bash
# backend KHÔNG --reload (WatchFiles miss trên ổ mạng)
uvicorn src.main:app --host 127.0.0.1 --port 8001

TOKEN=$(curl -s -X POST http://127.0.0.1:8001/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"engineer@example.com","password":"password123"}' | jq -r .access_token)

curl -s -X POST http://127.0.0.1:8001/api/v1/ingest -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"input_path":"samples/hospital","database_id":1,"dialect":null}'

# /graph: 8 bảng raw có column_schemas (declared), staging/mart có (propagated)
curl -s "http://127.0.0.1:8001/api/v1/graph?database_id=1" -H "Authorization: Bearer $TOKEN"

# /impact: đổi kiểu DECIMAL -> INTEGER trên cột đã khai báo
curl -s "http://127.0.0.1:8001/api/v1/impact/raw_invoices?direction=downstream&database_id=1&column=amount_billed&change_kind=type&target_type=INTEGER" \
  -H "Authorization: Bearer $TOKEN"
# schema_note ~ "Cột `amount_billed`: kiểu `DECIMAL(12, 2)`, NOT NULL. THU HẸP thập phân -> nguyên — rủi ro CAO..."
```

## 10. Commit

```
3ca76fc feat(impact): phủ đủ 8 change_kind cho cạnh control lineage
efd7c47 feat(impact): column type + constraint từ DDL nguồn, risk note schema-aware
5759bf2 test(fe): adapter maps column_schemas -> ColumnDef
5ff73c0 fix(storage): round-trip dependency_kind + dedup cạnh lúc load
290aef1 feat(impact): gom kết quả theo QUAN HỆ bảng, bỏ risk note lặp
3c952eb style(impact): tách định danh cột vào chip nền đen
5eead69 harden(impact): propagation chỉ mang data_type, +19 test siết biên
d886f70 refactor(impact): làm gọn code chấm rủi ro, chống phình combinatorial
6868166 docs(impact): writeup + WORKLOG
dc29eab fix(schema): DROP TABLE không xoá column_schema (test e2e phát hiện)
```
