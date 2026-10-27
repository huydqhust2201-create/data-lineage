# Project Brief — DATA-04: AI Agent tự động sinh & duy trì Data Lineage

> Gate G1 deliverable — 1-page brief. Team P-116.

## Vấn đề (Problem)

Trong tổ chức có nhiều pipeline dữ liệu (ETL/dbt/SQL script), theo thời gian không ai còn nắm rõ luồng dữ liệu chảy từ đâu đến đâu. Khi kỹ sư dữ liệu sửa hoặc xóa một cột trong bảng, họ **không biết** báo cáo, dashboard hay bảng nào khác đang phụ thuộc vào cột đó — sửa xong thì hàng loạt báo cáo bị lỗi mà không ai lường trước được (breaking change không kiểm soát được).

## Giải pháp (Solution)

Một AI Agent đọc trực tiếp code SQL/dbt từ một repo/folder do người dùng chỉ định, tự động:

1. Parse SQL/dbt để trích quan hệ phụ thuộc **table-level** giữa các bảng (ưu tiên chính; column-level là mở rộng nếu còn thời gian)
2. Dùng LLM xử lý các trường hợp parser thuần (sqlglot/sqllineage) không đọc được — dynamic SQL, Jinja macro phức tạp
3. Dựng đồ thị lineage (directed graph), lưu bằng NetworkX
4. Trả lời truy vấn **impact analysis**: sửa cột X ảnh hưởng bảng/báo cáo nào (downstream), hoặc cột Y tính từ đâu (upstream)
5. Với cạnh quan hệ mà LLM không chắc chắn (confidence thấp), yêu cầu con người xác nhận (HITL) trước khi ghi chính thức vào đồ thị

## Target User

- **Primary:** Data Engineer / Analytics Engineer trong team dữ liệu vừa và nhỏ, đang maintain nhiều dbt model/SQL script mà không có công cụ lineage thương mại (dùng bản mã nguồn mở dbt project `jaffle_shop` để phát triển sớm, chờ xác nhận đối tác thật)
- **Secondary:** Data Analyst cần tra cứu nhanh "báo cáo này phụ thuộc bảng nào" trước khi báo cáo lỗi

## Key Features (MVP)

| # | Feature | Ghi chú |
|---|---------|---------|
| 1 | Ingest từ path tường minh (local folder / cloned repo) | Không tự động dò tìm database |
| 2 | Parser-first extraction (sqlglot/sqllineage) + LLM fallback | Log rõ nhánh nào xử lý case nào |
| 3 | Impact analysis API (downstream/upstream, đa tầng) | Table-level trước |
| 4 | HITL confirm cho cạnh confidence thấp | Ngưỡng mặc định 0.8, cấu hình được |
| 5 | Trực quan hóa đồ thị (react-flow), highlight impact khi query | Frontend |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Agent | LangGraph + LangChain |
| Backend | FastAPI |
| Parser | sqlglot / sqllineage |
| LLM | OpenAI GPT-4o-mini (mặc định template — xác nhận lại với mentor nếu đổi) |
| Graph Storage | NetworkX (MVP), cân nhắc Neo4j nếu cần persist |
| Frontend | React + react-flow |
| SQL Dialect | Postgres (mặc định) |

## Ngoài phạm vi (Out of scope cho MVP)

Column-level lineage đầy đủ mọi transform, tự động sửa lỗi pipeline, tích hợp real-time với warehouse production, hỗ trợ mọi SQL dialect, quản lý phân quyền doanh nghiệp. Chi tiết: xem [PRD.md](PRD.md#6-non-goals--out-of-scope).

## Team

| Member | Vai trò |
|--------|---------|
| Đỗ Quang Huy | Team Lead — LangGraph orchestration, impact analysis design, kiến trúc |
| Nguyễn Thành Công | SQL Parser (sqlglot/sqllineage) — ground-truth dataset |
| Đỗ Đức Trường | LLM extraction — prompt engineering, đánh giá precision/recall |
| Lê Huy Hoàng | Graph storage (BFS/DFS, NetworkX CRUD) + Frontend react-flow |

## Tài liệu liên quan

- [PRD.md](PRD.md) — yêu cầu chi tiết, user stories, success metrics
- [wireframe.md](wireframe.md) — màn hình & user flow
- [ARCHITECTURE.md](../ARCHITECTURE.md) — kiến trúc hệ thống
