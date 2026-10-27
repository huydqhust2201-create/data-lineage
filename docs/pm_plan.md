# PM Plan — DATA-04 Data Lineage Agent (Team Baby Sharks)

> Tài liệu quản lý dự án, bám theo [Project Charter](https://docs.google.com/spreadsheets/d/1Es72Khi1MtSQOSdbfdf7FuLvYwxUcz3m). Mentor: Lê Văn Thể. Mục tiêu SMART: agent chạy đúng trên 10-15 pipeline thực tế, độ chính xác 80-85%, trả lời impact query trong vài giây — trong 6 tuần.

## 1. Lộ trình 6 tuần

Ngày ước tính dựa trên charter lập 29/7 — **khớp lại với ngày thật khi BTC công bố deadline từng Gate**, đây chỉ là mốc để team tự bám.

| Tuần | Mốc (charter) | Việc cụ thể | Ai làm | Kiến thức cần học |
|---|---|---|---|---|
| **W1** (28/7-3/8) | Project Charter + Gate G1 | Charter, Brief, PRD, Wireframe, setup repo/AI log, dựng contract chung (schema/state/config/stub service) | Huy (lead), cả team review | Git branching, Pydantic cơ bản, TypedDict, đọc hiểu PRD |
| **W2** (4-10/8) | Solution Design | Code thật cho 3 service: parse SQL, LLM extraction, graph storage/BFS-DFS | Công / Trường / Hoàng | sqlglot (parse cây cú pháp SQL), prompt engineering + structured output, thuật toán đồ thị (DAG, BFS/DFS) |
| **W3** (11-17/8) | **Demo 1** | Nối 3 service vào LangGraph pipeline thật, API impact analysis, demo chạy được end-to-end trên vài file SQL mẫu | Huy nối graph + API, cả team fix bug | LangGraph (node/edge/state), FastAPI routing |
| **W4-W5** (18-31/8) | Hoàn thiện & Deploy | Thêm HITL review UI, graph visualization (react-flow), chạy thử trên 10-15 pipeline thật/gần thật, đo precision/recall, deploy | Hoàng (frontend), Trường (đo eval), Huy (deploy) | React + react-flow, Docker/CI-CD, cách đo precision/recall |
| **W6** (1-7/9) | Đánh giá cuối kỳ | Video demo, pitch deck, hoàn thiện JOURNAL/WORKLOG/eval report | Cả team | Không có kiến thức mới — tổng hợp trình bày |

## 2. Đang ở đâu (thật, tính đến hôm nay)

- ✅ W1 xong: Charter + Gate G1 (brief/PRD/wireframe) đã nộp, contract chung đã merge vào `main`
- ✅ Đã bắt đầu sớm W2: Công code xong `parser_service.py` + ground-truth test, đã merge
- 🔲 Trường (LLM extraction), Hoàng (graph storage) đang code trên nhánh riêng, chưa merge
- ⚠️ Vướng CI (GitHub Actions) của org bị lỗi billing — không chặn code, chỉ chặn auto-check, đã báo Admin

## 3. Vì sao mỗi phần kiến thức lại cần (giải thích ngắn cho người mới)

- **sqlglot / parse SQL**: câu lệnh SQL là văn bản, muốn biết "cột A phụ thuộc cột B" thì phải biến văn bản đó thành cây cú pháp (giống cây phân tích ngữ pháp câu văn) rồi đọc cây đó — sqlglot làm việc này thay vì tự viết regex (regex dễ sai với SQL phức t​tạp)
- **LLM + structured output**: có những đoạn SQL quá lắt léo (dbt macro, dynamic SQL) mà sqlglot đọc không ra — lúc đó dùng LLM "đoán" quan hệ phụ thuộc, nhưng bắt LLM trả lời theo đúng khuôn `LineageEdge` (Pydantic) để không nhận về văn bản tự do khó xử lý
- **Đồ thị (NetworkX, BFS/DFS)**: sau khi có các quan hệ phụ thuộc, cần lưu thành mạng lưới (node = bảng/cột, edge = quan hệ) rồi duyệt xuôi/ngược để trả lời "sửa cái này ảnh hưởng gì" — đây là bài toán đồ thị kinh điển, không cần tự nghĩ ra thuật toán, NetworkX có sẵn
- **LangGraph**: agent cần chạy qua nhiều bước có điều kiện (nếu parser fail thì gọi LLM, nếu confidence thấp thì dừng chờ người duyệt) — LangGraph là công cụ dựng "sơ đồ luồng xử lý" đó thay vì viết if/else lồng nhau khó bảo trì
- **FastAPI**: là lớp để bên ngoài (frontend, người dùng) gọi vào agent qua HTTP, không phải chạy agent trực tiếp trong terminal
- **react-flow**: thư viện vẽ đồ thị dạng node-edge trên web, dùng để người dùng nhìn thấy trực quan sơ đồ lineage thay vì đọc danh sách text

## 4. Rủi ro cần theo dõi (từ charter + phát sinh thực tế)

| Rủi ro | Tình trạng | Hướng xử lý |
|---|---|---|
| Parser không đọc được nhiều case SQL | Đang xây ground-truth để đo sớm | Công tiếp tục thêm case đa dạng trong `tests/ground_truth/` |
| LLM hallucination (bịa quan hệ sai) | Đã có cơ chế confidence + HITL | Trường cần đo precision/recall thật khi có kết quả |
| Scope creep | Chưa xảy ra | Bám đúng bảng in/out scope trong charter, không tự thêm feature |
| Vắng mặt nhân sự | Chưa xảy ra | Theo dõi qua WORKLOG hằng ngày |
| CI bị chặn do billing org | **Đang xảy ra** | Đã báo Admin, không phải lỗi team, không chặn việc code/merge |

## 5. Cách quản lý hằng ngày/hằng tuần

- **Hằng ngày**: cập nhật `WORKLOG.md` (ai làm gì, kết quả gì)
- **Hằng tuần**: cập nhật `JOURNAL.md` (mục tiêu, khó khăn, bài học) + `/weekly submit` cho mentor
- **Code**: mỗi module 1 nhánh riêng từ `main`, PR nhỏ, review trước khi merge (đã áp dụng từ Gate G1)
- **Trước Demo 1 (W3)**: checklist — pipeline chạy hết đầu-cuối trên ít nhất 3-5 file SQL mẫu, API impact query trả kết quả đúng, có log rõ nhánh parser vs LLM
