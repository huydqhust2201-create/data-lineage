# PRD — DATA-04: AI Agent tự động sinh & duy trì Data Lineage

> Product Requirements Document. Gate G1 deliverable. Team P-116.
> Version: 0.1 (draft cho Gate G1) — Ngày: 2026-08-02

## 1. Overview

Data Engineer trong tổ chức mất khả năng theo dõi luồng phụ thuộc giữa các bảng/cột khi số lượng pipeline SQL/dbt tăng lên. Sản phẩm là một AI Agent tự động đọc source code (không đọc dữ liệu thật trong database), trích xuất quan hệ phụ thuộc, dựng đồ thị lineage, và trả lời truy vấn "impact analysis" — giúp kỹ sư biết trước hậu quả trước khi sửa/xóa một cột.

## 2. Problem Statement

- Không ai nắm được đầy đủ bức tranh phụ thuộc dữ liệu khi số lượng SQL/dbt model tăng theo thời gian
- Sửa/xóa 1 cột có thể làm vỡ nhiều báo cáo downstream mà không có cảnh báo trước
- Các công cụ lineage thương mại (Atlan, Monte Carlo...) tốn phí và triển khai phức tạp cho team nhỏ; dbt docs chỉ lineage trong phạm vi dbt, không cover raw SQL script rời rạc

## 3. Goals & Success Metrics

| Goal | Metric | Target (MVP) |
|------|--------|---------------|
| Trích lineage đúng ở mức table | Precision/Recall trên bộ ground-truth tự viết | ≥ 80% cả hai |
| Phân biệt rõ nguồn gốc cạnh | % cạnh có `source_type` (parser/llm) + `confidence` | 100% |
| Impact query đủ nhanh để dùng tương tác | Latency truy vấn downstream/upstream | < 3s trên đồ thị demo |
| Không tự động tin sai LLM | % cạnh confidence thấp được đưa qua HITL trước khi ghi chính thức | 100% |
| Test coverage cho phần lõi (parser/graph) | pytest coverage `services/` | > 60% |

## 4. Target Users & Personas

- **Primary — Data/Analytics Engineer:** maintain nhiều dbt model/SQL script, cần biết "sửa cột này ảnh hưởng gì" trước khi merge PR
- **Secondary — Data Analyst:** cần tra cứu nhanh "báo cáo X phụ thuộc bảng/cột nào" khi debug số liệu sai

## 5. User Stories

| ID | User Story | Ưu tiên |
|----|-----------|---------|
| US-1 | Là Data Engineer, tôi muốn cung cấp đường dẫn folder/repo SQL để agent phân tích, để không phải tự đọc từng file | Must |
| US-2 | Là Data Engineer, tôi muốn agent tự parse SQL bằng công cụ thuần trước, chỉ gọi LLM khi parser fail, để tiết kiệm chi phí và tăng độ tin cậy | Must |
| US-3 | Là Data Engineer, tôi muốn xem cạnh nào do LLM suy luận và confidence bao nhiêu, để biết mức độ tin tưởng | Must |
| US-4 | Là Data Engineer, tôi muốn xác nhận/từ chối các cạnh confidence thấp trước khi chúng được ghi chính thức, để tránh lineage sai | Must |
| US-5 | Là Data Engineer, tôi muốn hỏi "sửa cột X ảnh hưởng bảng/báo cáo nào" (downstream), để đánh giá rủi ro trước khi thay đổi | Must |
| US-6 | Là Data Analyst, tôi muốn hỏi "cột Y được tính từ đâu" (upstream), để debug số liệu sai | Must |
| US-7 | Là Data Engineer, tôi muốn xem đồ thị lineage trực quan và được highlight phần bị ảnh hưởng khi truy vấn, để hiểu nhanh hơn bảng chữ | Should |
| US-8 | Là mentor/BTC, tôi muốn thấy log rõ ràng request nào agent tự parse được, request nào phải nhờ LLM, để đánh giá được kiến trúc | Should |

## 6. Functional Requirements

- **FR-1 Ingest:** API nhận `input_path` (bắt buộc, không tự dò tìm), quét file `.sql`/dbt model trong path đó
- **FR-2 Parse:** Với mỗi file, thử `sqlglot`/`sqllineage` trước → sinh `LineageEdge(source_type="parser", confidence=1.0)`
- **FR-3 LLM fallback:** File/statement parser fail (dynamic SQL, Jinja macro chưa compile...) → đưa qua LLM extraction, sinh `LineageEdge(source_type="llm", confidence<1.0)`, kèm log rõ lý do fallback
- **FR-4 HITL review:** Cạnh có `confidence < confidence_threshold` (config, mặc định 0.8) → đưa vào hàng đợi chờ xác nhận; chỉ ghi vào đồ thị chính thức sau khi được confirm
- **FR-5 Graph build:** Toàn bộ cạnh đã xác nhận được ghi vào đồ thị (NetworkX), tách biệt hoàn toàn khỏi DB nguồn
- **FR-6 Impact analysis API:** `GET /impact/{table}?column=&direction=downstream|upstream` trả về danh sách bảng/cột bị ảnh hưởng, đa tầng (transitive). **Response tách rõ 2 khối `confirmed` (chắc chắn) vs `inferred_pending` (LLM suy luận, chưa qua HITL) — không bao giờ gộp chung** (US-3, US-4). Mỗi cạnh kèm `evidence`: cạnh parser có `file_path`/`raw_sql`/`line_range`; cạnh LLM có thêm `reasoning`/`fallback_reason`
- **FR-6b Auto overview graph:** `POST /ingest` trả kèm `overview_graph` (table-level, chỉ các bảng vừa phát hiện lượt này) — không cần user submit impact query trước mới thấy được bức tranh tổng
- **FR-7 Graph visualization:** Hiển thị đồ thị (vd react-flow nếu có frontend), highlight node/edge liên quan khi user submit 1 impact query — hiện chưa có frontend (đã gỡ, xem quyết định trong repo), chỉ có API
- **FR-8 Schema verify (tùy chọn):** Nếu cần xác minh schema thật, chỉ query `information_schema` qua kết nối read-only riêng biệt — không trộn với luồng đọc code chính
- **FR-9 Workspace & database isolation (thêm 2026-08-23):** Đồ thị lineage, mô tả, hàng
  đợi HITL và DDL preview được cô lập theo `database_id` (không còn 1 đồ thị toàn cục
  dùng chung) — giải quyết vấn đề ingest nhiều dự án lẫn lộn không phân biệt được SQL
  của dự án nào. Mỗi `database` thuộc 1 `workspace`; user cần là `database_members` mới
  truy cập được, role `engineer` (đọc/ghi) hoặc `viewer` (chỉ đọc + chat). Danh tính hiện
  tại chỉ qua header `X-User-Id` chọn từ seed user có sẵn — chưa phải login production
  (không password/JWT), xem non-goal mục 9

## 7. Non-Functional Requirements

- **Tách nguồn sự thật:** Source of truth là code, không phải data trong database production
- **Không hardcode:** model name, SQL dialect, confidence threshold nằm trong `src/config.py` (Pydantic Settings), đọc từ `.env`
- **Khả năng giải trình:** mọi lần gọi LLM (input/output) được log lại — vừa phục vụ debug, vừa khớp yêu cầu AI Usage Logging của chương trình
- **Kiểm thử:** mọi hàm xử lý SQL/graph có unit test trong `tests/`, đối chiếu `tests/ground_truth/`
- **Bảo mật:** không kết nối ghi vào database production; kết nối `information_schema` (nếu có) là read-only riêng biệt

## 8. Technical Decisions (theo dõi ở đây, không lặp lại trong code comment)

| Quyết định | Trạng thái |
|---|---|
| Graph storage: NetworkX vs Neo4j | **Chốt MVP: NetworkX** cho traversal (BFS/DFS, in-memory, đơn giản) + **Postgres** cho persist (quyết định 2026-08-06, xem `storage_service.py`) — giải quyết vấn đề nhiều worker process không nhất quán dữ liệu; cân nhắc Neo4j sau nếu cần graph query phức tạp hơn |
| SQL dialect | **Chốt MVP: Postgres**; mở rộng dialect khác nếu còn thời gian |
| LLM provider | Mặc định OpenAI GPT-4o-mini theo template; cần xác nhận với mentor nếu đổi |
| Nguồn dữ liệu test | **Chốt 2026-08-05: dùng dbt project mã nguồn mở [`jaffle-shop`](https://github.com/dbt-labs/jaffle-shop)** (vendor trong `samples/jaffle-shop/`), không chờ đối tác thật nữa — 13 model khớp mục tiêu 10-15 pipeline trong charter |
| Ngưỡng confidence HITL | Mặc định **0.8**, để trong config, không hardcode |
| Cô lập dữ liệu đa dự án | **Chốt 2026-08-23**: thay vì gắn nhãn `project` nhẹ trên từng cạnh (thử ở PR #75, sau đó bị bỏ), chuyển hẳn sang mô hình `workspace` → `database` → `database_members` (role engineer/viewer) — mọi dữ liệu (graph, mô tả, HITL, DDL preview) cô lập theo `database_id`. Đây là scope-creep thật so với non-goal gốc (mục 9), nhưng chỉ dừng ở mức "phân biệt dữ liệu theo database + 2 role", không xây login/JWT production. PR #76-78, merge thẳng không qua review — cần review lại nếu mở rộng thêm |

## 9. Non-Goals / Out of Scope

- Column-level lineage đầy đủ cho mọi loại transform phức tạp
- Tự động sửa lỗi pipeline khi phát hiện breaking change
- Tích hợp real-time với data warehouse production (chỉ demo trên script/dữ liệu mẫu)
- Hỗ trợ mọi SQL dialect
- Đăng nhập/bảo mật cấp production (password, JWT, SSO, audit log) — **sửa 2026-08-23**:
  team đã thêm mô hình cô lập dữ liệu theo workspace/database (xem FR-9, mục 8) vì
  nhu cầu thực tế phân biệt SQL theo dự án khi ingest, nhưng danh tính vẫn chỉ là
  seed user qua header `X-User-Id`, không phải hệ thống authz/bảo mật doanh nghiệp
  đầy đủ — mục non-goal gốc ("quản lý phân quyền/bảo mật dữ liệu mức doanh nghiệp")
  được thu hẹp lại thành mục này thay vì loại bỏ hoàn toàn

## 10. Risks & Open Questions

| Risk / Question | Ảnh hưởng | Hướng xử lý |
|---|---|---|
| ~~Chưa có đối tác/dữ liệu thật để test~~ — **Đã giải quyết 2026-08-05**: team quyết định dùng hẳn open source `jaffle-shop` làm dữ liệu test chính thức, không chờ đối tác | Có thể lineage đúng trên `jaffle-shop` nhưng sai trên SQL thực tế phức tạp hơn ở nơi khác | Xây ground-truth đa dạng case (join, CTE, window function) song song; lưu ý các file `.sql` trong `jaffle-shop` là dbt Jinja template (`{{ ref() }}`/`{{ source() }}`), cần tiền xử lý trước khi đưa qua sqlglot — xem `samples/jaffle-shop/README.md` |
| LLM fallback có thể tốn chi phí/chậm nếu nhiều file parser fail | Latency ingest, chi phí API | Giới hạn batch size, cache kết quả theo hash file |
| Ngưỡng confidence 0.8 chưa có cơ sở thực nghiệm | Có thể quá chặt (nhiều HITL thủ công) hoặc quá lỏng (sai nhiều) | Đo precision/recall theo từng ngưỡng trong `eval/`, điều chỉnh sau |

## 11. Team & Ownership

| Member | Module chính |
|--------|--------------|
| Đỗ Quang Huy (Lead) | LangGraph orchestration (`agents/graph.py`), Impact analysis API |
| Nguyễn Thành Công | Parser service (`services/parser_service.py`) + ground-truth dataset |
| Đỗ Đức Trường | LLM extraction (prompt + Pydantic schema) + eval precision/recall |
| Lê Huy Hoàng | Graph storage (`services/graph_service.py`, BFS/DFS) + Frontend react-flow |
