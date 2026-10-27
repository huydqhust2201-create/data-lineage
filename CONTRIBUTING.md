# Quy trình làm việc — Team Baby Sharks (DATA-04)

> Ghi lại cách team đang code với nhau, để ai cũng biết chứ không chỉ nằm trong lịch sử chat.

## Phân công module (PRD.md mục 11)

| Ai | Module | File chính |
|---|---|---|
| Đỗ Quang Huy (Lead) | LangGraph orchestration, impact analysis API | `src/agents/graph.py`, `src/api/routes.py` |
| Nguyễn Thành Công | SQL Parser + ground-truth | `src/services/parser_service.py`, `tests/ground_truth/` |
| Đỗ Đức Trường | LLM extraction + eval | `src/services/` (llm extraction), `eval/` |
| Lê Huy Hoàng | Graph storage + Frontend | `src/services/graph_service.py`, `src/services/storage_service.py`, frontend react-flow |

## Nguyên tắc "contract trước, code sau"

Trước khi code 1 module, đọc trước 3 file này — đây là "hợp đồng" chung, đừng tự đổi type khi chưa bàn với cả team vì người khác đang code dựa vào đó:
- `src/models/schemas.py` — `LineageEdge`, `IngestRequest/Response`, `GraphResponse`...
- `src/agents/state.py` — `LineageAgentState`
- `docs/api_contract.md` — endpoint nào nhận/trả gì

Nếu cần đổi field trong các file trên, báo trong nhóm chat trước khi sửa — vì 1 thay đổi ở đây ảnh hưởng tất cả các nhánh khác.

## Nhánh & PR

1. Luôn tạo nhánh mới từ `main` mới nhất: `git checkout main && git pull && git checkout -b feature/<module>-<mô-tả>`
   (ví dụ: `feature/sql-parser`, `feature/llm-extraction`, `feature/graph-storage`)
2. Không push thẳng vào `main` — luôn qua PR
3. Trước khi mở PR, chạy tại máy mình:
   ```bash
   pytest tests/ -v
   ruff check src/ tests/
   ```
   PR không được có test đỏ hoặc lint lỗi
4. PR nhỏ theo từng module/function, không gộp nhiều việc không liên quan vào 1 PR
5. Merge xong thì `git checkout main && git pull` trước khi tạo nhánh tiếp theo

## Setup môi trường (lần đầu)

```bash
python -m venv .venv
.venv/Scripts/activate   # Windows
pip install -r requirements.txt
cp .env.example .env     # rồi điền OPENROUTER_API_KEY, JWT_SECRET
```

## Coding convention

- Có type hint đầy đủ cho hàm public (khớp tiêu chí chấm Code Quality của BTC)
- Không hardcode model name / SQL dialect / confidence threshold — thêm vào `src/config.py` (Pydantic Settings), đọc qua `get_settings()`
- Mọi hàm xử lý SQL hoặc graph phải có test trong `tests/`; nếu liên quan parser, đối chiếu với `tests/ground_truth/` (xem README ở đó)
- Mọi lần gọi LLM (extraction) phải log input/output — vừa để debug, vừa khớp yêu cầu AI Usage Logging của chương trình

## Báo cáo

- `WORKLOG.md` — cập nhật hằng ngày (ai làm gì, kết quả gì)
- `JOURNAL.md` — cập nhật hằng tuần (mục tiêu, khó khăn, bài học)
- `docs/pm_plan.md` — lộ trình 6 tuần, xem để biết đang ở mốc nào
