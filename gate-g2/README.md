# DATA-04 — Lineage AI

> Data Engineer/Analyst mất khả năng theo dõi phụ thuộc giữa các bảng/cột khi số lượng pipeline SQL/dbt tăng lên → AI Agent tự động đọc **source code SQL/dbt** (không đọc dữ liệu thật), dựng đồ thị lineage, và trả lời "sửa/xoá cột này ảnh hưởng gì" trong vài giây.

VinUni AI20K Build Phase — Team **Baby Sharks** (P-116) · Mentor: Lê Văn Thể

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
                                        │
                                        ▼
                     FastAPI (/impact, /graph, /chat) ──▶ Frontend (React + @xyflow/react)
```

Toàn bộ pipeline chạy trong LangGraph (`src/agents/graph.py`): `parse → llm_extract (nếu cần) → hitl → graph_build`. Chatbot dùng 1 graph LangGraph **riêng** (`build_chat_graph()`), không lẫn với pipeline ingest.

## Tech Stack

| Layer | Công nghệ |
|-------|-----------|
| AI Agent | LangGraph + LangChain, OpenRouter (GPT-4o-mini) |
| Parser | sqlglot |
| Graph | NetworkX (in-memory traversal) + PostgreSQL (persist, JSONB evidence) |
| Backend | FastAPI + Uvicorn, Pydantic v2 |
| Frontend | React 19 + TypeScript + Vite + `@xyflow/react` (không dùng elkjs — tự viết layout để giữ bundle nhẹ) |
| Testing | pytest + pytest-asyncio, ruff, mypy |
| DevOps | Docker (Postgres), GitHub Actions |

## Cấu trúc dự án

```
├── src/
│   ├── agents/
│   │   ├── graph.py        # build_graph() (ingest) + build_chat_graph() (chatbot) — tách biệt hoàn toàn
│   │   ├── state.py        # LineageAgentState (TypedDict)
│   │   ├── nodes/          # lineage_nodes.py, query_nodes.py
│   │   ├── tools/          # impact_tools.py — tool cho chatbot ReAct
│   │   └── chat/           # base/guard/registry/resolve/session cho agent chat
│   ├── api/routes.py       # 10 endpoint REST, xem bảng bên dưới
│   ├── models/schemas.py   # Pydantic — nguồn sự thật cho mọi contract (BE lẫn FE)
│   ├── services/           # parser, llm_extraction, graph, storage, review, chat
│   ├── config.py           # Pydantic Settings, đọc từ .env — không hardcode
│   └── main.py
├── frontend/                # React + Vite, xem frontend/README.md
├── tests/                   # pytest + tests/ground_truth/ (bộ SQL mẫu đo precision/recall)
├── docs/                    # PRD, api_contract, pm_plan, wireframe, guide (10 chương)
├── eval/                    # kết quả đo precision/recall
├── samples/                 # jaffle-shop (dbt project mã nguồn mở) — dữ liệu test chính thức
├── scripts/                 # AI Usage Logging hooks (bắt buộc theo BTC)
├── Dockerfile, docker-compose.yml
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
# Mở .env — điền OPENROUTER_API_KEY, AI_LOG_API_KEY riêng của team
```

### 2. Cài AI Logging hooks (bắt buộc — chạy 1 lần)

```bash
# Windows
powershell -ExecutionPolicy Bypass -File scripts\setup_hooks.ps1
# Linux / macOS / Git Bash
bash scripts/setup_hooks.sh
```

### 3. Chạy Postgres (lưu đồ thị lineage)

```bash
docker compose up -d db
```

Postgres map ra cổng **5435** (không phải 5432 mặc định — máy dev hay bị native Postgres/container khác chiếm 5432/5433). `.env.example` đã khớp sẵn `DATABASE_URL=postgresql://lineage:lineage@localhost:5435/lineage`; nếu 5435 cũng bị chiếm trên máy bạn, đổi cả 2 nơi (`.env` và `docker-compose.yml` mục `db.ports`) cho khớp nhau.

### 4. Chạy backend

```bash
make run
# tương đương: uvicorn src.main:app --reload --host 127.0.0.1 --port 8001
```

- Swagger UI: http://127.0.0.1:8001/docs
- Dùng cổng **8001** (không phải 8000 — hay bị 1 tool khác chiếm) và bind **127.0.0.1** tường minh (không dùng `localhost` — Windows có thể resolve ra `::1` trước, gây "connection refused" dù server đang chạy).
- `--reload` sinh ra 2 process (supervisor + worker) — nếu cần tắt tay trên Windows, phải kill cả 2 PID (`Get-NetTCPConnection -LocalPort 8001 | Select OwningProcess`), kill thiếu 1 cái sẽ để lại process cũ phục vụ dữ liệu stale.

### 5. Chạy frontend

```bash
cd frontend
npm install
npm run dev
```

- Mở http://127.0.0.1:5173
- Vite dev server đã proxy sẵn `/api` và `/health` sang `127.0.0.1:8001` (`frontend/vite.config.ts`) — không cần cấu hình CORS thủ công lúc dev.

## API Endpoints (10)

| Method | Path | Dùng cho |
|--------|------|----------|
| POST | `/api/v1/ingest` | Phân tích SQL theo đường dẫn thư mục trên server |
| POST | `/api/v1/ingest/upload` | Upload file/thư mục `.sql` thật từ máy người dùng (multipart) |
| GET | `/api/v1/graph` | Toàn bộ đồ thị lineage đã xác nhận (Lineage Explorer) |
| DELETE | `/api/v1/graph` | Xoá sạch đồ thị lineage tích luỹ (Danger Zone) |
| GET | `/api/v1/impact/{table}` | Impact analysis — tách sẵn `confirmed` / `inferred_pending` |
| GET | `/api/v1/pending-review` | Danh sách cạnh chờ duyệt (HITL) |
| POST | `/api/v1/pending-review/{edge_id}/confirm` | Duyệt 1 cạnh — ghi chính thức vào đồ thị |
| POST | `/api/v1/pending-review/{edge_id}/reject` | Từ chối 1 cạnh suy luận sai |
| POST | `/api/v1/chat` | Lineage Copilot — hỏi đáp bằng ngôn ngữ tự nhiên |
| GET | `/api/v1/status` | Trạng thái hệ thống (API/Graph/Database/Agent) |
| GET | `/health` | Health check (ngoài `/api/v1`) |

Contract chi tiết từng field: [`docs/api_contract.md`](docs/api_contract.md).

**Nguyên tắc xuyên suốt:** `confirmed` (parser, chắc chắn) và `inferred_pending`/`pending` (LLM suy luận, chờ duyệt) **luôn tách biệt rõ ràng ở mọi endpoint** — không bao giờ gộp chung. Đây là bug thật đã từng xảy ra (`overview_graph` gộp nhầm) và đã fix + có regression test.

## Sample Queries

Backend chạy ở `127.0.0.1:8001` (xem Quick Start). 3 ví dụ dùng ngay bằng `curl` — request/response thật khớp `docs/api_contract.md`.

**1. Ingest — phân tích 1 thư mục SQL (dùng dbt project mẫu có sẵn trong repo):**
```bash
curl -X POST http://127.0.0.1:8001/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"input_path": "samples/jaffle-shop", "dialect": null}'
```
Trả về `IngestResponse` — số file/cạnh tìm được, và `overview_graph` (bức tranh table-level của lượt ingest này, tách sẵn `confirmed_edges`/`pending_edges`).

**2. Impact analysis — "sửa/xoá bảng `orders` thì ảnh hưởng gì phía sau":**
```bash
curl "http://127.0.0.1:8001/api/v1/impact/orders?direction=downstream"
```
Trả về `ImpactQueryResult` — tách rõ `confirmed` (chắc chắn) và `inferred_pending` (LLM suy luận, kèm evidence + lý do), không bao giờ gộp chung.

**3. Chat — hỏi bằng ngôn ngữ tự nhiên** (agent trả lời đúng ngôn ngữ của câu hỏi — ví dụ dưới dùng tiếng Anh vì `curl -d` với tiếng Việt có dấu dễ vỡ encoding trên PowerShell/Git Bash Windows; hỏi tiếng Việt vẫn hoạt động bình thường qua Swagger UI `/docs` hoặc frontend):
```bash
curl -X POST http://127.0.0.1:8001/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What breaks if orders changes?", "session_id": null}'
```
Trả về `ChatResponse` — văn xuôi `answer` + fact có cấu trúc trong `confirmed`/`inferred_pending`, giữ lại `session_id` để hỏi tiếp cùng ngữ cảnh (vd khi cần làm rõ tên bảng qua `clarification_options`).

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

## Phân công công việc (PRD.md mục 11)

| Thành viên | Vai trò | Module chính |
|---|---|---|
| **Đỗ Quang Huy** (Lead) | LangGraph orchestration, Impact analysis API, tích hợp toàn bộ pipeline, deploy | `src/agents/graph.py`, `src/api/routes.py` |
| **Nguyễn Thành Công** | SQL Parser tĩnh + bộ ground-truth đo precision/recall | `src/services/parser_service.py`, `tests/ground_truth/` |
| **Đỗ Đức Trường** | LLM extraction fallback (prompt + structured output) + eval | `src/services/llm_extraction_service.py`, `eval/` |
| **Lê Huy Hoàng** | Graph storage (NetworkX/BFS-DFS) + Frontend (React + react-flow) | `src/services/graph_service.py`, `src/services/storage_service.py`, `frontend/` |

Lộ trình 6 tuần đầy đủ + trạng thái hiện tại: [`docs/pm_plan.md`](docs/pm_plan.md).

## Quy trình làm việc

Nhánh mới từ `main` mới nhất → code → `pytest` + `ruff check` sạch tại máy → PR → review → merge → `git pull` trước khi tạo nhánh tiếp theo. Không push thẳng vào `main`. Chi tiết + nguyên tắc "đọc contract trước khi code" (`schemas.py`, `state.py`, `api_contract.md`): [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Deliverables

| # | Deliverable | Vị trí |
|---|-------------|--------|
| 1 | Source Code | `src/`, `frontend/` |
| 2 | README.md | file này |
| 3 | Architecture Diagram | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| 4 | AI Logs | LangSmith + Auto AI Usage Logging (`.ai-log/`) |
| 5 | Live URL | *(chưa deploy — kế hoạch W4-W5)* |
| 6 | Video Demo | Đã nộp qua link riêng (không lưu trong repo) |
| 7 | Pitch Deck | Đã nộp qua link riêng (không lưu trong repo) |
| 8 | Development Journal | [`JOURNAL.md`](JOURNAL.md) |
| 9 | Worklog | [`WORKLOG.md`](WORKLOG.md) |
| 10 | Evaluation Evidence | `eval/` — eval tự động ([`pipeline_eval.md`](eval/results/pipeline_eval.md)) + [`manual_test_cases.md`](eval/manual_test_cases.md) (6 test case tay, backend live thật) |

## AI Usage Logging

Bắt buộc theo BTC — đã cấu hình sẵn hooks tự động cho Claude Code, Cursor, Codex, Gemini CLI, Antigravity, GitHub Copilot (`.claude/`, `.cursor/`, `.codex/`, `.gemini/`, `.agents/`, `.github/hooks/`). Log ghi vào `.ai-log/session.jsonl`, tự động submit khi `git push`. Chạy `scripts/setup_hooks.sh` (hoặc `.ps1`) một lần sau khi clone nếu chưa cài.

ChatGPT/web tools khác — log thủ công:
```bash
bash scripts/_pyrun.sh scripts/log_manual.py --tool chatgpt --prompt "What you asked"
```

## Liên kết

- 📖 Technical Guidebook: [phoenix.note.transformerlabs.ai/technical-book](https://phoenix.note.transformerlabs.ai/technical-book)
- 🏫 VinUni AI20K Build Phase — Team Baby Sharks (P-116)
- 👨‍🏫 Mentor: Lê Văn Thể

## License

MIT — Sử dụng tự do cho mục đích giáo dục.
