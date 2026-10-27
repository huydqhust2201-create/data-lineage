# DATA-04 — Lineage AI

> Data Engineer/Analyst mất khả năng theo dõi phụ thuộc giữa các bảng/cột khi số lượng pipeline SQL/dbt tăng lên → AI Agent tự động đọc **source code SQL/dbt** (không đọc dữ liệu thật), dựng đồ thị lineage, và trả lời "sửa/xoá cột này ảnh hưởng gì" trong vài giây.

VinUni AI20K Build Phase — Team **Baby Sharks** (P-116) · Mentor: Lê Văn Thể

> **Về repo này.** Đây là bản tiếp nối cá nhân của dự án nhóm Baby Sharks; repo gốc của nhóm
> là private và giữ toàn bộ lịch sử commit. Phần ứng dụng là công sức chung của cả nhóm — xem
> bảng đóng góp ngay bên dưới. Những phần tôi làm thêm sau khi dự án nhóm kết thúc: tầng
> observability (Prometheus, Grafana, Loki — [docs/monitoring.md](docs/monitoring.md)) và lab
> Kubernetes tự dựng bằng kubeadm ([docs/k8s-lab.md](docs/k8s-lab.md)).

## Thành viên & Phân công công việc

Kế hoạch phân công gốc nằm ở [PRD.md mục 11](docs/PRD.md) (chốt ở Gate G1, 2026-08-02). Trong quá trình build, phạm vi mỗi người đã mở rộng đáng kể so với kế hoạch ban đầu — bảng dưới đây phản ánh **đóng góp thực tế theo lịch sử commit của repo gốc**, không phải bản kế hoạch tĩnh.

| Thành viên | Vai trò ban đầu (PRD) | Vai trò thực tế |
|---|---|---|
| **Đỗ Quang Huy** (Lead) | LangGraph orchestration, Impact Analysis API | Giữ đúng vai trò gốc và mở rộng thêm: orchestration pipeline ingest lineage (`src/agents/graph.py`) và API layer (30 endpoint, `src/api/`), tích hợp frontend↔backend end-to-end, cùng phần lớn tính năng giai đoạn sau — multi-hop column-aware impact traversal, change_kind risk mapping, RAG mô tả cột, HITL duyệt tại chỗ, blast-radius graph, quản lý đa dự án + lịch sử ingest, tự phát hiện breaking change, tự động re-ingest |
| **Nguyễn Thành Công** | SQL Parser tĩnh + bộ ground-truth đo precision/recall | **Chuyển trọng tâm sang dựng lại toàn bộ giao diện frontend** (Sidebar, Workspace Hub, Overview Dashboard, Lineage Explorer, HITL Dashboard, SQL Ingest Scanner). Việc parser + ground-truth ban đầu vẫn giữ nguyên trong `src/services/parser_service.py`/`tests/ground_truth/` |
| **Đỗ Đức Trường** | LLM extraction (prompt + structured output) + eval | Xây dựng LLM lineage extraction và evaluation (`src/services/llm_extraction_service.py`, `eval/`); xây dựng trọn bộ chatbot orchestration bằng LangGraph, gồm guard, resolve, session và các tool truy vấn lineage/impact, asset, mô tả, DDL preview (`src/agents/chat/`, `src/agents/nodes/query_nodes.py`, `src/agents/tools/`, `src/agents/graph.py`, `src/services/chat_service.py`); RAG sinh mô tả và tìm kiếm bảng (`src/services/description_service.py`, `src/services/asset_service.py`); phân quyền và cô lập dữ liệu theo database (`src/api/auth_routes.py`, `src/api/database_routes.py`, `src/services/database_service.py`, `src/services/storage_service.py`). |
| **Lê Huy Hoàng** | Graph storage (NetworkX/BFS-DFS) + Frontend react-flow | Trang Impact Analysis: mở rộng risk mapping đủ 6 loại thao tác thay đổi (trước chỉ 2), nối "Downstream Blast Radius" vào dữ liệu thật thay số liệu giả, benchmark latency theo tiêu chí PRD |

Lộ trình 6 tuần đầy đủ + trạng thái hiện tại: [`docs/pm_plan.md`](docs/pm_plan.md).

## Vấn đề & Giải pháp

- Không ai nắm được đầy đủ bức tranh phụ thuộc dữ liệu khi số lượng SQL/dbt model tăng theo thời gian; sửa/xoá 1 cột có thể làm vỡ nhiều báo cáo downstream mà không có cảnh báo trước.
- Công cụ lineage thương mại (Atlan, Monte Carlo...) tốn phí và triển khai phức tạp cho team nhỏ; `dbt docs` chỉ lineage trong phạm vi dbt, không cover raw SQL script rời rạc.
- **Giải pháp:** agent parse SQL bằng `sqlglot` trước (chắc chắn 100%, `source_type=parser`), chỉ gọi LLM khi parser fail (dynamic SQL, Jinja macro...) và luôn gắn `confidence` (`source_type=llm`). Cạnh confidence thấp phải qua **Human-in-the-loop** trước khi được ghi chính thức vào đồ thị — không bao giờ tự tin sai LLM. Mọi cạnh đều kèm **evidence** (file/dòng/SQL gốc hoặc lý do LLM suy luận) để người dùng tự thẩm định.

Chi tiết đầy đủ: [`docs/PRD.md`](docs/PRD.md) · Kiến trúc: [`ARCHITECTURE.md`](ARCHITECTURE.md)

## Kiến trúc tổng quan

```
SQL/dbt files ──▶ parser_service (sqlglot) ──fail──▶ llm_extraction_service (GPT-4o-mini)
                          │                                      │
                          └────────────┬─────────────────────────┘
                                        ▼
                          confidence < 0.8 ──▶ review_service (HITL queue)
                                        │
                                        ▼ (đã xác nhận)
                          graph_service (NetworkX, BFS/DFS) ──persist──▶ Postgres
                                        │  └─▶ tự phát hiện breaking change (bảng bị
                                        │      drop/rename nhưng còn downstream tham chiếu)
                                        ▼
                          describe / describe_columns (RAG — mô tả nghiệp vụ + embedding
                          BGE-M3, chỉ chạy khi DESCRIPTION_ENABLED=true)
                                        │
                                        ▼
     FastAPI (30 endpoint, RBAC theo workspace/database) ──▶ Frontend (React + @xyflow/react)
```

Toàn bộ pipeline ingest chạy trong 1 LangGraph (`src/agents/graph.py::build_graph()`): `parse → llm_extract (nếu cần) → hitl → graph_build → describe → describe_columns`. Chatbot dùng 1 graph LangGraph **riêng** (`build_chat_graph()`: `agent → tools → compose → verify`, vòng lặp ReAct có giới hạn số bước/tool call), không lẫn với pipeline ingest.

Ngoài ra có 1 vòng lặp nền độc lập (`ingest_watcher.py`, tắt mặc định — `AUTO_REINGEST_ENABLED`) tự phát hiện file `.sql` đổi mtime và tự ingest lại, không cần user bấm nút mỗi lần.

## Tech Stack

| Layer | Công nghệ |
|-------|-----------|
| AI Agent | LangGraph + LangChain, OpenRouter (GPT-4o-mini) |
| Parser | sqlglot (đã xử lý dbt Jinja: `ref`/`source`/`config`, macro thuần, snapshot block, dynamic SQL) |
| Graph | NetworkX (in-memory traversal, multi-hop column-aware) + PostgreSQL (persist, JSONB evidence) |
| Semantic search | BGE-M3 qua HuggingFace TEI (self-host, Docker) + pgvector — mô tả nghiệp vụ bảng/cột (tắt mặc định, `DESCRIPTION_ENABLED`) |
| Backend | FastAPI + Uvicorn, Pydantic v2 |
| Auth | Đăng nhập thật: email/mật khẩu (bcrypt hash) hoặc Google OAuth (ID token, xác minh qua `google-auth`) → JWT (`pyjwt`, HS256) → mọi request kèm `Authorization: Bearer <token>`. RBAC 2 vai trò (engineer/viewer) theo database, xem [Auth & Multi-tenancy](#auth--multi-tenancy) |
| Frontend | React 19 + TypeScript + Vite + `@xyflow/react` (không dùng elkjs — tự viết layout để giữ bundle nhẹ) |
| Testing | pytest + pytest-asyncio, ruff, mypy |
| DevOps | Docker + Docker Compose (Postgres + pgvector, TEI embeddings, Caddy reverse-proxy), GitHub Actions CI (ruff + pytest) → CD deploy qua SSH có approval gate, AWS EC2 |
| Observability | Prometheus (histogram tự viết, không thêm dependency) + Grafana (dashboard provisioned as code) + Loki/Alloy (log JSON tập trung) — xem [docs/monitoring.md](docs/monitoring.md) |

## Cấu trúc dự án

```
├── src/
│   ├── agents/
│   │   ├── graph.py        # build_graph() (ingest, 6 node) + build_chat_graph() (chatbot, 4 node) — tách biệt hoàn toàn
│   │   ├── state.py        # LineageAgentState / ChatAgentState (TypedDict)
│   │   ├── nodes/          # lineage_nodes.py (ingest + breaking-change detection), query_nodes.py (chat)
│   │   ├── tools/          # 9 tool cho chatbot ReAct: graph/impact/asset/description/ddl_preview/sql_document (RAG trên SQL đã ingest)
│   │   └── chat/           # base/guard/registry/resolve/session cho agent chat
│   ├── api/                # routes.py (22 endpoint, xem bảng bên dưới) + auth_routes.py (đăng nhập/đăng ký) + database_routes.py + deps.py (JWT + RBAC)
│   ├── models/schemas.py   # Pydantic — nguồn sự thật cho mọi contract (BE lẫn FE)
│   ├── services/           # parser, llm_extraction, graph, storage, review, chat, ingest,
│   │                       # ingest_watcher (auto re-ingest), description/embedding (RAG),
│   │                       # sql_document (RAG trên SQL đã ingest), auth/user, database, asset (catalog)
│   ├── config.py           # Pydantic Settings, đọc từ .env — không hardcode
│   └── main.py              # FastAPI app + lifespan (khởi động ingest_watcher nếu bật)
├── frontend/                # React + Vite, xem frontend/README.md
├── tests/                   # pytest + tests/ground_truth/ (bộ SQL mẫu đo precision/recall)
├── docs/                    # PRD, api_contract, pm_plan, wireframe, guide (10 chương)
├── eval/                    # kết quả đo precision/recall
├── samples/                 # jaffle-shop (dbt project mã nguồn mở) — dữ liệu test chính thức
├── scripts/                 # AI Usage Logging hooks (bắt buộc theo BTC) + seed_auth.py
├── Dockerfile, docker-compose.yml   # backend + Postgres (pgvector) + TEI embeddings
└── ARCHITECTURE.md, CONTRIBUTING.md, JOURNAL.md, WORKLOG.md
```

## Quick Start — chạy toàn bộ stack

Cần: Python 3.11+, Node.js 18+, Docker (cho Postgres).

### 1. Setup môi trường Python

```bash
# Windows
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
# macOS / Linux
python3.11 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Mở .env — điền OPENROUTER_API_KEY và JWT_SECRET
# (đổi thành chuỗi ngẫu nhiên dài — dùng cho đăng nhập, xem Auth & Multi-tenancy)
```

### 2. Chạy Postgres (lưu đồ thị lineage)

```bash
docker compose up -d db
```

Postgres map ra cổng **5435** (không phải 5432 mặc định — máy dev hay bị native Postgres/container khác chiếm 5432/5433). `.env.example` đã khớp sẵn `DATABASE_URL=postgresql://lineage:lineage@localhost:5435/lineage`; nếu 5435 cũng bị chiếm trên máy bạn, đổi cả 2 nơi (`.env` và `docker-compose.yml` mục `db.ports`) cho khớp nhau.

### 2b. Seed user/workspace/database mặc định (bắt buộc — chạy 1 lần)

```bash
python scripts/seed_auth.py
```

Tạo sẵn 2 tài khoản đăng nhập được thật (`engineer@example.com` / `viewer@example.com`, mật khẩu `password123`) và 1 database `default` — cần có trước khi gọi bất kỳ API nào (mọi endpoint đòi `Authorization: Bearer <token>` lấy từ `POST /auth/login` + `database_id` hợp lệ, xem [Auth & Multi-tenancy](#auth--multi-tenancy)). Chạy lại an toàn (idempotent) — kể cả với user đã tồn tại từ trước khi có tính năng mật khẩu, script tự vá mật khẩu còn thiếu.

### 2c. (Tuỳ chọn) Bật RAG mô tả bảng/cột

Mặc định **tắt** (`DESCRIPTION_ENABLED=false`) — không cần bước này nếu chỉ demo lineage/impact/HITL cơ bản. Muốn bật semantic search theo mô tả nghiệp vụ:

```bash
# 1 lần: tải model BGE-M3 (~2.2GB) vào volume mà container embeddings đọc
pip install huggingface_hub
hf download BAAI/bge-m3 --local-dir data/tei/bge-m3
docker compose up -d embeddings   # HuggingFace TEI, đọc model từ data/tei/bge-m3, xem docker-compose.yml
```

rồi đặt `DESCRIPTION_ENABLED=true` trong `.env`.

### 3. Chạy backend

```bash
make run
# tương đương: uvicorn src.main:app --reload --host 127.0.0.1 --port 8001
```

- Swagger UI: http://127.0.0.1:8001/docs
- Dùng cổng **8001** (không phải 8000 — hay bị 1 tool khác chiếm) và bind **127.0.0.1** tường minh (không dùng `localhost` — Windows có thể resolve ra `::1` trước, gây "connection refused" dù server đang chạy).
- `--reload` sinh ra 2 process (supervisor + worker) — nếu cần tắt tay trên Windows, phải kill cả 2 PID (`Get-NetTCPConnection -LocalPort 8001 | Select OwningProcess`), kill thiếu 1 cái sẽ để lại process cũ phục vụ dữ liệu stale.

### 4. Chạy frontend

```bash
cd frontend
npm install
npm run dev
```

- Mở http://127.0.0.1:5173
- Vite dev server đã proxy sẵn `/api` và `/health` sang `127.0.0.1:8001` (`frontend/vite.config.ts`) — không cần cấu hình CORS thủ công lúc dev.

## API Endpoints (32 + `/health`)

Mọi endpoint dưới `/api/v1` (trừ `/auth/register`, `/auth/login`, `/auth/google`) yêu cầu header `Authorization: Bearer <token>` (JWT lấy từ đăng nhập, xem [Auth & Multi-tenancy](#auth--multi-tenancy)) và tham số `database_id` — dữ liệu lineage cô lập hoàn toàn theo từng database.

**Ingest**

| Method | Path | Dùng cho |
|--------|------|----------|
| POST | `/api/v1/ingest` | Phân tích SQL theo đường dẫn thư mục trên server |
| POST | `/api/v1/ingest/upload` | Upload file/thư mục `.sql` thật từ máy người dùng (multipart) |
| GET | `/api/v1/ingest-runs` | Lịch sử các lượt ingest của 1 database (path, số file/cạnh, thời gian) |

**Graph & Impact Analysis**

| Method | Path | Dùng cho |
|--------|------|----------|
| GET | `/api/v1/graph` | Toàn bộ đồ thị lineage đã xác nhận (Lineage Explorer) |
| DELETE | `/api/v1/graph` | Xoá sạch đồ thị lineage tích luỹ (Danger Zone) |
| GET | `/api/v1/impact/{table}` | Impact analysis đa tầng, tới tận cấp cột — tách sẵn `confirmed` / `inferred_pending`, kèm `hops` (tầng), `risk` (khi truyền `change_kind`) |

**HITL — duyệt cạnh lineage**

| Method | Path | Dùng cho |
|--------|------|----------|
| GET | `/api/v1/pending-review` | Danh sách cạnh chờ duyệt |
| POST | `/api/v1/pending-review/{edge_id}/confirm` | Duyệt 1 cạnh — ghi chính thức vào đồ thị |
| POST | `/api/v1/pending-review/{edge_id}/reject` | Từ chối 1 cạnh suy luận sai |

**Breaking-change alerts** (tự phát hiện lúc ingest, không cần user tự paste DDL)

| Method | Path | Dùng cho |
|--------|------|----------|
| GET | `/api/v1/breaking-change-alerts` | Cảnh báo bảng bị drop/rename nhưng vẫn còn bảng downstream tham chiếu |
| POST | `/api/v1/breaking-change-alerts/{alert_id}/acknowledge` | Đánh dấu đã xử lý 1 cảnh báo |

**Mô tả nghiệp vụ (RAG, tắt mặc định — `DESCRIPTION_ENABLED`)**

| Method | Path | Dùng cho |
|--------|------|----------|
| GET | `/api/v1/descriptions/pending` | Mô tả bảng LLM sinh, confidence thấp, chờ duyệt |
| POST / GET | `/api/v1/descriptions/{node_id}/confirm` \| `/reject` \| `PUT` | Duyệt / từ chối / sửa tay mô tả bảng |
| GET | `/api/v1/column-descriptions/pending` | Mô tả cột LLM sinh, chờ duyệt |
| POST / PUT | `/api/v1/column-descriptions/{node_id}/{column}/confirm` \| `/reject` \| `PUT` | Duyệt / từ chối / sửa tay mô tả cột |

**Chat & Status**

| Method | Path | Dùng cho |
|--------|------|----------|
| POST | `/api/v1/chat` | Lineage Copilot — ReAct agent với 9 tool (tìm bảng theo tên/mô tả, downstream/upstream, xem asset, preview DDL breaking change, tìm nội dung SQL đã ingest...) |
| POST | `/api/v1/chat/reset` | Xoá lịch sử hội thoại của user hiện tại trên 1 database, bắt đầu phiên chat mới |
| GET | `/api/v1/status` | Trạng thái hệ thống (API/Graph/Database/Agent) |
| GET | `/health` | Health check (ngoài `/api/v1`) |

**Auth & Database** (xem [Auth & Multi-tenancy](#auth--multi-tenancy))

| Method | Path | Dùng cho |
|--------|------|----------|
| POST | `/api/v1/auth/register` | Đăng ký tài khoản mới bằng email/mật khẩu, trả JWT |
| POST | `/api/v1/auth/login` | Đăng nhập bằng email/mật khẩu, trả JWT |
| POST | `/api/v1/auth/google` | Đăng nhập bằng Google ID token (xác minh qua `google-auth`), tự tạo/liên kết tài khoản, trả JWT |
| GET | `/api/v1/auth/me` | Thông tin user hiện tại |
| GET | `/api/v1/users` | Danh sách user (yêu cầu đăng nhập) |
| GET | `/api/v1/databases` | Danh sách database user có quyền truy cập (owner hoặc được mời) |
| POST | `/api/v1/databases` | Tạo database mới, người tạo là owner với role `engineer` |
| GET / POST / DELETE | `/api/v1/databases/{database_id}/members[/{user_id}]` | Xem / mời / xoá thành viên 1 database, role `engineer` hoặc `viewer` |

Contract chi tiết từng field: [`docs/api_contract.md`](docs/api_contract.md).

**Nguyên tắc xuyên suốt:** `confirmed` (parser, chắc chắn) và `inferred_pending`/`pending` (LLM suy luận, chờ duyệt) **luôn tách biệt rõ ràng ở mọi endpoint** — không bao giờ gộp chung. Đây là bug thật đã từng xảy ra (`overview_graph` gộp nhầm) và đã fix + có regression test.

## Auth & Multi-tenancy

Mỗi user sở hữu nhiều `database` (= 1 project độc lập — dữ liệu lineage, mô tả, hàng đợi HITL, breaking-change alert cô lập hoàn toàn theo `database_id`, không lẫn giữa các project; frontend gom các database của 1 user lại thành "Workspace Hub", nhưng đây thuần là cách trình bày ở FE — backend không có bảng/khái niệm `workspace` riêng). User truy cập 1 database với role `engineer` (đọc/ghi) hoặc `viewer` (chỉ đọc + chat).

Đăng nhập thật, 2 cách:
- **Email/mật khẩu**: `POST /auth/register` (mật khẩu hash bằng `bcrypt`, tối thiểu 8 ký tự) rồi `POST /auth/login`.
- **Google**: frontend lấy Google ID token qua `@react-oauth/google` (Google Identity Services), gửi lên `POST /auth/google` — backend xác minh chữ ký/audience bằng thư viện `google-auth`, tự tạo tài khoản mới hoặc liên kết vào tài khoản email trùng đã có.

Cả 2 cách đều trả về JWT (`pyjwt`, HS256, hạn dùng `JWT_EXPIRES_MINUTES`, mặc định 1440 phút). Mọi request tới các endpoint còn lại phải kèm `Authorization: Bearer <token>` — `current_user()` xác minh chữ ký + hạn dùng, không còn cơ chế nào tin header do client tự khai (`X-User-Id` đã bị loại bỏ hoàn toàn). Seed 2 tài khoản mặc định qua `python scripts/seed_auth.py` (xem Quick Start bước 3b). Muốn dùng đăng nhập Google cần tự tạo OAuth Client ID (Web application) trên Google Cloud Console, điền `GOOGLE_CLIENT_ID` (backend, `.env`) và `VITE_GOOGLE_CLIENT_ID` (frontend, `frontend/.env.local`) — nút Google tự ẩn trên màn đăng nhập nếu chưa cấu hình.

## Sample Queries

Backend chạy ở `127.0.0.1:8001`, đã seed user + database mặc định (Quick Start bước 3b). Mọi request cần header `Authorization: Bearer <token>` và `database_id` (id database seed, mặc định `1` nếu chạy lần đầu trên máy mới) — 4 ví dụ dùng ngay bằng `curl`, request/response thật khớp `docs/api_contract.md`.

**0. Đăng nhập — lấy JWT (bước bắt buộc trước mọi request khác):**
```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "engineer@example.com", "password": "password123"}' | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
```

**1. Ingest — phân tích 1 thư mục SQL (dùng dbt project mẫu có sẵn trong repo):**
```bash
curl -X POST http://127.0.0.1:8001/api/v1/ingest \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"input_path": "samples/jaffle-shop", "database_id": 1, "dialect": null}'
```
Trả về `IngestResponse` — số file/cạnh tìm được, `overview_graph` (bức tranh table-level của lượt ingest này, tách sẵn `confirmed_edges`/`pending_edges`), và `description_pending_count`.

**2. Impact analysis — "sửa/xoá bảng `orders` thì ảnh hưởng gì phía sau, tới tận cấp cột":**
```bash
curl "http://127.0.0.1:8001/api/v1/impact/orders?direction=downstream&database_id=1&column=id" \
  -H "Authorization: Bearer $TOKEN"
```
Trả về `ImpactQueryResult` — tách rõ `confirmed` (chắc chắn) và `inferred_pending` (LLM suy luận, kèm evidence + lý do), mỗi cạnh kèm `hops` (tầng) và `transform_type`, không bao giờ gộp chung.

**3. Chat — hỏi bằng ngôn ngữ tự nhiên** (agent luôn trả lời bằng tiếng Việt, giữ nguyên tên bảng/cột; ví dụ dưới dùng tiếng Anh trong nội dung câu hỏi vì `curl -d` với tiếng Việt có dấu dễ vỡ encoding trên PowerShell/Git Bash Windows — hỏi tiếng Việt vẫn hoạt động bình thường qua Swagger UI `/docs` hoặc frontend):
```bash
curl -X POST http://127.0.0.1:8001/api/v1/chat \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"question": "What breaks if orders changes?", "database_id": 1}'
```
Trả về `ChatResponse` — văn xuôi `answer` (lồng cả mô tả nghiệp vụ nếu RAG đã bật, không chỉ liệt kê sự kiện cấu trúc) + fact có cấu trúc trong `confirmed`/`inferred_pending`. Không còn cần tự quản lý `session_id` — danh tính hội thoại lấy từ `(database_id, user trong token)`, lịch sử vài lượt gần nhất tự nhớ lại (kiểu Claude Code, xem `src/agents/chat/session.py`); `POST /chat/reset` xoá lịch sử để bắt đầu phiên mới.

Đầy đủ field + ví dụ nhiều lượt (làm rõ tên bảng, HITL confirm/reject...): [`docs/api_contract.md`](docs/api_contract.md).

## Testing & Lint

```bash
make check      # lint + format + test, hoặc chạy riêng:
make test        # pytest tests/ -v
make lint         # ruff check
make typecheck    # mypy src/

cd frontend && npm run typecheck && npm run build   # frontend
```

Ground-truth precision/recall: `tests/ground_truth/` + `eval/`.

Một số test trong `tests/test_services/test_storage_service.py` xoá sạch bảng lineage trên `DATABASE_URL` đang cấu hình — **skip mặc định** để tránh vô tình xoá dữ liệu dev/demo thật, chỉ chạy khi set `PYTEST_ALLOW_DB_WIPE=1` (CI hoặc Postgres bỏ đi được, không phải Postgres dev).

## Quy trình làm việc

Nhánh mới từ `main` mới nhất → code → `pytest` + `ruff check` sạch tại máy → PR → review → merge → `git pull` trước khi tạo nhánh tiếp theo. Không push thẳng vào `main`. Chi tiết + nguyên tắc "đọc contract trước khi code" (`schemas.py`, `state.py`, `api_contract.md`): [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Deliverables

| # | Deliverable | Vị trí |
|---|-------------|--------|
| 1 | Source Code | `src/`, `frontend/` |
| 2 | README.md | file này |
| 3 | Architecture Diagram | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| 4 | AI Logs | LangSmith tracing (hook log AI của khoá học đã được gỡ khỏi bản cá nhân này) |
| 5 | Live URL | *(chưa deploy — kế hoạch W4-W5)* |
| 6 | Video Demo | Đã nộp qua link riêng (không lưu trong repo) |
| 7 | Pitch Deck | Đã nộp qua link riêng (không lưu trong repo) |
| 8 | Development Journal | [`JOURNAL.md`](JOURNAL.md) |
| 9 | Worklog | [`WORKLOG.md`](WORKLOG.md) |
| 10 | Evaluation Evidence | `eval/` — eval tự động ([`pipeline_eval.md`](eval/results/pipeline_eval.md)) + [`manual_test_cases.md`](eval/manual_test_cases.md) (6 test case tay, backend live thật) |

## Liên kết

- 📖 Technical Guidebook: [phoenix.note.transformerlabs.ai/technical-book](https://phoenix.note.transformerlabs.ai/technical-book)
- 🏫 VinUni AI20K Build Phase — Team Baby Sharks (P-116)
- 👨‍🏫 Mentor: Lê Văn Thể

## License

MIT — Sử dụng tự do cho mục đích giáo dục.
