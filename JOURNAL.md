# Weekly Journal — Team [Tên Team]

> Ghi lại mỗi tuần: học được gì, khó khăn gì, quyết định gì, kế hoạch tiếp.

---

## Week 1: [Ngày bắt đầu] - [Ngày kết thúc]

### Mục tiêu tuần này
- [ ] [Mục tiêu 1]
- [ ] [Mục tiêu 2]
- [ ] [Mục tiêu 3]

### Đã hoàn thành
- [thành quả 1]
- [thành quả 2]

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| [mô tả] | [cách xử lý] | [output] |

### Bài học
- [bài học 1]
- [bài học 2]

### Kế hoạch tuần sau
- [ ] [task 1]
- [ ] [task 2]

---

## Week 2: [Ngày bắt đầu] - [Ngày kết thúc]

### Mục tiêu tuần này
- [ ] [Mục tiêu 1]

### Đã hoàn thành
-

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| | | |

### Bài học
-

### Kế hoạch tuần sau
-

---

## Week 3: 11/08/2026 - 17/08/2026

### Mục tiêu tuần này
- [x] Nối 3 service (parser, LLM extraction, graph storage) vào pipeline LangGraph thật, chạy được end-to-end
- [x] API impact analysis đầy đủ 2 chiều (upstream/downstream), tách rõ `confirmed` vs `inferred_pending` kèm evidence
- [x] Demo được trên file SQL thật ngoài đời (không chỉ fixture ground-truth), verify qua HTTP thật
- [ ] Frontend hoàn thiện và merge vào `main` — PR #31 đang mở, chờ duyệt phần hình ảnh/UX trước khi merge

### Đã hoàn thành
- Merge chatbot agent (PR #23) — trả lời câu hỏi lineage bằng ngôn ngữ tự nhiên, tách riêng confirmed/inferred_pending
- Thêm `POST /ingest/upload` (PR #28) — upload file/thư mục `.sql` thật từ máy người dùng, thay vì phải gõ đường dẫn server
- Fix bug thật: `overview_graph` gộp lẫn cạnh confirmed và pending, khiến confirm nhầm 1 cạnh đã confirmed thì lỗi 404 (PR #22) — tách thành `confirmed_edges`/`pending_edges` riêng
- Fix bug thật: `sqlglot.parse_one()` chỉ đọc đúng 1 câu lệnh trong cả file, âm thầm bỏ qua phần còn lại của file DDL nhiều statement (PR #29) — phát hiện khi test bằng file SQL thật (schema phòng khám nha khoa), không phải fixture dbt 1-statement/file
- Thêm `DELETE /graph` + nút "Xoá đồ thị" (PR #30) — sau khi xác nhận việc ingest nhiều lần cộng dồn vào 1 đồ thị là đúng thiết kế (không phải bug), thêm lối thoát thủ công để reset khi demo/test
- Rebuild frontend 2 lần trong tuần: lần 1 theo hướng Gemini-green (đủ 9 endpoint, chat-centric, upload thật, đồ thị kiểu Atlan), lần 2 (PR #31) viết lại hoàn toàn theo spec chi tiết + ảnh tham khảo Atlan/DataHub/dbt Cloud — sidebar 8 trang, Lineage Explorer/Impact Analysis dùng React Flow, Review Queue (HITL), Settings > Danger Zone
- Review kỹ và merge toàn bộ PR của team: parser + ground-truth test data (Công), chatbot (Trường)
- Dọn hạ tầng dev: chuẩn hoá port 8001/5435 xuyên suốt Makefile/README/docker-compose, fix nhầm tài khoản git tác giả

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| `overview_graph` gộp chung cạnh confirmed + pending, lấy nhầm `edge_id` gọi confirm bị 404 | Tách `OverviewGraph.confirmed_edges`/`pending_edges` riêng | PR #22 merged, có test regression tái hiện đúng bug |
| Đồ thị hiển thị "linh tinh" không khớp file SQL vừa ingest | Truy ra 2 nguyên nhân: (1) Postgres còn tồn dữ liệu test cũ, (2) `sqlglot.parse_one()` chỉ đọc 1 statement/file | Xoá dữ liệu cũ + fix parser dùng `sqlglot.parse()` xử lý từng statement, verify lại bằng file SQL thật |
| `uvicorn --reload` để lại tiến trình con (supervisor + worker) không kill hết, vẫn phục vụ dữ liệu cũ dù đã sửa code/DB | Xác định đúng cặp process qua `Win32_Process`, kill cả 2, bỏ `--reload` khi test thủ công | Backend luôn phản ánh đúng code/DB mới nhất |
| Ingest nhiều file riêng biệt bị gộp chồng vào 1 đồ thị, ban đầu tưởng là bug | Xác nhận đây là hành vi đúng thiết kế (lineage toàn dự án phải cộng dồn qua nhiều lần ingest) | Chỉ thêm `DELETE /graph` thủ công thay vì tự động xoá — giữ đúng bản chất công cụ lineage |

### Bài học
- Nguyên tắc "chắc chắn (confirmed/parser) tách biệt hoàn toàn khỏi chưa chắc (pending/LLM)" phải giữ nhất quán ở MỌI lớp — schema, service, UI. Gộp nhầm 1 lần đã gây bug thật, phải rà lại toàn bộ luồng liên quan để tránh lặp lại sai lầm tương tự chỗ khác
- Ground-truth test (fixture dbt 1-statement/file) không đủ để bắt hết lỗi — chỉ khi test bằng file SQL thật ngoài đời (nhiều statement, DDL lẫn DML) mới lộ ra giả định sai của parser
- Trên Windows, `uvicorn --reload` sinh ra 1 cặp tiến trình (supervisor + worker); kill nhầm 1 tiến trình vẫn để sót data cũ — cần kiểm tra command line thật qua `Win32_Process` khi nghi ngờ có tiến trình "ma"

### Kế hoạch tuần sau
- [ ] Duyệt phần hình ảnh/UX của PR #31 (frontend mới) rồi merge vào `main`
- [ ] Dọn PR #25 (nhánh chatbot cũ, đã được thay thế bởi #23 đã merge)
- [ ] Chạy thử agent trên 10-15 pipeline thật/gần thật (không chỉ ground-truth fixtures), đo precision/recall thật
- [ ] Cập nhật lại `docs/pm_plan.md` mục "2. Đang ở đâu" — đang viết từ giữa W2, chưa phản ánh khối lượng việc đã xong tuần này
- [ ] Bắt đầu W4: HITL review UI đã có, chuyển sang deploy thật (Docker/CI-CD)

---

## Week 4: 18/08/2026 - 24/08/2026

### Mục tiêu tuần này
- [x] Đào sâu column-level lineage: lan truyền filter theo cột qua nhiều hop (trước đây chỉ đúng ở hop đầu)
- [x] Nâng RAG: mở rộng table description + semantic search (đồng đội) xuống tận mức cột, cùng vòng đời HITL/CAS đầy đủ
- [x] Thêm `change_kind` — map rủi ro theo `transform_type` khi hỏi "đổi kiểu dữ liệu/giá trị cột X thì sao"
- [x] Nối frontend mới (rewrite toàn bộ, PR #60) với backend thật — Lineage Explorer, Impact Analysis, Ingest

### Đã hoàn thành
- Fix bug thật: `os.path.relpath()` crash `Internal Server Error` khi evidence file khác ổ đĩa với input_path trên Windows (PR #55)
- `_traverse()` (graph_service) giờ lan truyền filter cột qua nhiều hop bằng `active_columns` per-node, không rơi về table-level từ hop 2 như trước (PR #57)
- Thêm `change_kind: "type"|"value"` + bảng map rủi ro theo `transform_type` cho chat capability, sau đó mở luôn ra REST `GET /impact/{table}` để frontend dùng được (PR #61, #66)
- Mở rộng RAG xuống mức cột: bảng `lineage_column_descriptions` riêng, evidence từ cạnh confirmed hop đầu, `describe_columns_node` trong ingest pipeline, capability chat `search_column_description`, API `/column-descriptions/...` đầy đủ confirm/reject/human-override — mirror 100% vòng đời HITL của table description (PR #62)
- Merge + review kỹ 2 PR lớn của đồng đội: `fix/parse-dbt-target-node` (PR #59, kèm tool preview DDL impact) và rewrite frontend toàn bộ theo hướng enterprise data catalog (PR #60, +8327/-2422 dòng)
- Audit kỹ frontend mới: phát hiện ngoài Chat, toàn bộ UI (Lineage Explorer, Impact Analysis, HITL Dashboard*, Data Catalog, Overview, Ingest) đang chạy trên mock data hoặc bịa kết quả bằng string-matching dù đã gọi backend thật (*riêng HITL Dashboard hoá ra đã nối thật từ trước)
- Nối lại toàn bộ: Lineage Explorer/Impact/Catalog/Overview dùng `GET /graph` thật (PR #65), Impact Analysis hiện risk note thật từ `change_kind` (PR #66), Ingest dùng đúng `IngestResponse` thật thay vì bịa breakdown per-file (PR #67) — mỗi phase verify bằng Playwright thật (ingest jaffle-shop qua backend thật, chụp màn hình xác nhận không còn dữ liệu bịa)
- Fix bug thật: `.gitignore` có pattern `data/` không có `/` đầu, vô tình nuốt mất `frontend/src/data/mockProjects.ts` của PR #60 — khiến build FE lỗi `Cannot find module` mà tác giả không hề biết (PR #63)

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| PR #60 (frontend mới) build lỗi thật `Cannot find module './data/mockProjects'`, CI vẫn xanh | Truy ra `.gitignore` pattern `data/` áp dụng ở mọi độ sâu, nuốt mất `frontend/src/data/` | Đổi thành `/data/` (chỉ ignore root), báo tác giả bổ sung file, merge lại sạch |
| Frontend mới đẹp nhưng đa số tab chạy trên mock data dù nhìn qua tưởng đã nối backend (`queryRealImpact` được gọi nhưng kết quả chỉ nằm ở 1 box nhỏ, không drive UI chính) | Audit từng component bằng grep + đọc code thay vì tin ngoài mặt; verify lại bằng Playwright thật (ingest data thật, so tên bảng có khớp không) | Nối lại đúng 3 phase, có bằng chứng ảnh chụp cho từng phase |
| 2 PR (mình + tác giả PR #60) độc lập cùng sửa `.gitignore` theo cùng 1 hướng → conflict khi merge | Resolve merge cục bộ (chỉ khác phần comment), verify lại build trước khi push | Merge sạch, không mất thay đổi của bên nào |
| Nhiều lần `gh pr merge` bị vướng do có PR khác merge chen giữa lúc đang thao tác | Luôn `git status`/stash cẩn thận trước khi checkout, kiểm tra kỹ log trước khi merge thay vì chạy lệnh mù | Không mất code, phục hồi đúng trạng thái |

### Bài học
- CI hiện tại (`lint-and-test`) chỉ chạy cho backend Python, **không build frontend** — 1 PR frontend có thể pass CI xanh dù `npm run build` lỗi thật. Cần tự chạy `npm run build` thủ công trước khi merge bất kỳ PR frontend nào, không thể tin CI xanh là đủ.
- "Đã gọi API thật" khác với "UI hiển thị dữ liệu thật" — 1 component có thể gọi đúng endpoint thật nhưng kết quả bị bỏ xó ở 1 góc UI trong khi phần chính vẫn chạy trên dữ liệu giả lập. Phải verify bằng cách đọc kỹ code + chạy tay qua Playwright, không suy luận từ tên biến (`realImpactResult`) hay việc thấy đúng network call.
- `.gitignore` pattern không có `/` ở đầu áp dụng ở MỌI độ sâu trong repo — 1 pattern tưởng vô hại (`data/` để ignore data runtime của backend) có thể âm thầm nuốt file source code hợp lệ ở thư mục con khác hoàn toàn (`frontend/src/data/`), không có warning nào, tác giả PR không hề biết file mình "quên" là do git tự động bỏ qua.

### Kế hoạch tuần sau
- [ ] Thêm bước `npm run build` vào CI cho các PR đụng `frontend/` — tránh lặp lại lỗi PR #60
- [ ] Báo/theo dõi tác giả PR #60 bổ sung `frontend/src/data/mockProjects.ts` (đã fix gitignore, file giờ add được bình thường)
- [ ] Cân nhắc tiếp: Data Catalog/Overview Dashboard có cần nối sâu hơn (vd asset profile qua REST) hay giữ nguyên vì đã ăn theo `nodes`/`edges` thật
- [ ] Rà lại `docs/pm_plan.md` mục "Đang ở đâu" cho khớp khối lượng việc tuần này

---

<!-- Tiếp tục copy block trên cho Week 5, 6 -->
