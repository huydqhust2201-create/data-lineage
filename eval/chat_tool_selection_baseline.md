# Chat agent — compound-question baseline (PHẦN 0)

Ngày chạy: 2026-08-24. Mục tiêu: đo xem single-agent chat hiện tại (`agent → tools → compose → verify`,
xem [graph.py](../src/agents/graph.py)) có tự chọn đúng ≥2 nhóm tool khi câu hỏi thật sự cần hay không, trước
khi quyết định có đáng xây router + subagent (Phần 1) hay không.

Dữ liệu dùng để hỏi: project đã ingest thật `database_id=787` ("Jinjashop", dbt jaffle-shop demo) — 20 bảng,
45 cạnh lineage đã confirm, lấy qua `GET /api/v1/graph?database_id=787`. Không bịa tên bảng/cột.

4 nhóm tool:
| Nhóm | Tool |
|---|---|
| Resolver | `search_tables`, `list_relationships` |
| Impact | `downstream`, `upstream` |
| Description | `search_by_description`, `search_column_description` |
| DDL/General | `preview_ddl_impact`, `get_asset` |

## Kết quả 10 câu

| # | Ngôn ngữ | Nhóm cần | Tool thực gọi | Số bước | Thời gian | Kết quả |
|---|---|---|---|---|---|---|
| Q1 | VI | Impact, DDL | `downstream`, `preview_ddl_impact` | 2 | 7.5s | **FAIL** — trả lời cụt "Lineage đã ghi nhận: stg_orders", `answer_rejected_unknown_tables: order_total, total_amount` |
| Q2 | EN | Description, Impact | `search_column_description`×2, `search_tables`, `upstream` | 4 | 38.0s | **FAIL** — trả lời cụt "Lineage đã ghi nhận: customers", `answer_rejected_unknown_tables: customer_type` |
| Q3 | VI | Resolver, Impact | `search_by_description` (thay `search_tables`), `downstream`×5 | 6 | 17.6s | PASS (đúng nội dung) nhưng dùng sai nhóm tool + `budget_exhausted` (gọi thừa 4 lần `downstream` dò từng bảng ứng viên) |
| Q4 | EN | DDL/General, Impact | `search_tables`, `downstream`, `get_asset` | 3 | 11.4s | **PASS** — đủ nhóm, câu trả lời đầy đủ, không warning |
| Q5 | VI | Resolver, Description | `search_by_description`, `search_column_description` | 2 | 8.0s | **FAIL nặng** — cả 2 lần search đều trả rỗng dù `lifetime_spend` thực sự tồn tại (cạnh `orders→customers`), Resolver không được gọi, trả lời "chưa có cạnh nào" |
| Q6 | EN | Impact, Description | `upstream`, `get_asset` (thay `search_by_description`) | 2 | 7.6s | PASS (đúng nội dung) nhưng dùng sai nhóm tool cho phần "description" |
| Q7 | VI | DDL/General, Impact | `downstream`, `preview_ddl_impact` | 2 | 7.9s | **FAIL** — trả lời cụt "Lineage đã ghi nhận: stg_orders", `answer_rejected_unknown_tables: tax_paid` |
| Q8 | EN | Resolver, Impact | `search_by_description` (thay `search_tables`), `upstream`, `get_asset` | 3 | 9.0s | PASS (đúng nội dung) nhưng dùng sai nhóm tool |
| Q9 | VI | Description, Impact | `search_column_description`, `search_by_description`, `upstream` | 3 | 9.1s | PASS nhưng `budget_exhausted` (gọi 2 lần Description trùng lặp trước khi còn đủ ngân sách gọi Impact) |
| Q10 | EN | Resolver, DDL/General | `search_tables`, `preview_ddl_impact`×2 | 3 | 10.9s | **FAIL** — cả 2 nhóm tool đúng được gọi, nhưng câu trả lời cuối chỉ liệt kê tên bảng, không hề nói tới kết quả DDL preview; `budget_exhausted` + `answer_rejected_unknown_tables: discount_amount` |

Raw steps/latency/answer đầy đủ: `scratchpad/baseline_results.json` (không commit — chỉ đính kèm tham khảo).

## Phân loại lỗi

**Tỷ lệ "câu trả lời hỏng" thô: 5/10 = 50%** (Q1, Q2, Q5, Q7, Q10) — vượt ngưỡng 30% nêu trong yêu cầu.

Nhưng khi truy nguyên nguyên nhân gốc, lỗi rơi vào **đúng 2 nhóm nguyên nhân, không nhóm nào liên quan đến
việc agent gọi thiếu tool nhóm nào**:

1. **Bug ở `verify_node`/`unknown_mentions()` — false positive, gây ra Q1, Q2, Q7, Q10 (4/5 case FAIL).**
   [`src/agents/chat/guard.py:26-43`](../src/agents/chat/guard.py#L26): `TABLE_TOKEN` regex khớp bất kỳ
   token dạng `snake_case` nào trong câu trả lời và coi là "table mention". Nhưng
   [`_result_vocabulary()`](../src/agents/tools/impact_tools.py#L61) (dùng cho `downstream`/`upstream`) chỉ
   đưa `source_table`/`target_table` vào từ điển đã biết — **không** đưa `source_column`/`target_column`/
   `resolved_column` vào. Kết quả: mọi lúc LLM nhắc tên cột đang được hỏi (`order_total`, `tax_paid`,
   `customer_type`, `discount_amount`...) — điều hoàn toàn tự nhiên và đúng khi trả lời câu hỏi về đổi
   cột — `verify_node` coi đó là "unknown table", vứt bỏ câu trả lời đúng và thay bằng template cụt
   `_template_answer()`. Đây đã là 4/5 tổng số case fail đo được. Kiến trúc multi-agent (router + subagent)
   **không sửa được lỗi này** — lỗi nằm ở bước compose/verify chung, không phải ở việc chọn tool.

2. **Description search trả rỗng cho truy vấn hợp lệ — gây Q5.** `search_by_description("thong tin khach
   hang")` và `search_column_description("lifetime_spend")` đều trả 0 kết quả dù cạnh `orders.lifetime_spend
   → customers.lifetime_spend` có thật trong graph. Nhiều khả năng do bước `describe`/`describe_columns`
   (RAG mô tả nghiệp vụ) chưa từng chạy cho project 787, nên chưa có embedding nào để match — đây là lỗ hổng
   dữ liệu/coverage của pipeline mô tả, không phải lỗi điều phối tool.

3. **Ngân sách tool call hơi chật cho câu hỏi ghép thật.** `budget_exhausted` xuất hiện ở Q3, Q9, Q10 — agent
   cần 3-6 bước để trả lời trọn vẹn 1 câu ghép 2-nhóm, đôi khi hết ngân sách trước khi verify xong. Đây là vấn
   đề tinh chỉnh `chat_max_tool_calls`/`chat_max_agent_steps`, giải quyết được ngay trên **cùng một** agent.

**Về việc chọn nhóm tool theo đúng "chính tắc"**: 4/10 câu (Q3, Q6, Q8, và một phần Q5) agent dùng tool khác
nhóm dự kiến (vd `search_by_description` thay cho `search_tables`, hoặc `get_asset` thay cho
`search_by_description`) — nhưng 3/4 trường hợp đó (Q3, Q6, Q8) **vẫn ra câu trả lời đúng và đầy đủ**. Agent
đơn hiện tại đã tự linh hoạt "lách" sang tool liền kề nhóm khi cần, trong vòng lặp ReAct hiện có — không thấy
bằng chứng cho thấy thiếu router mới khiến các câu này thất bại.

## Kết luận & khuyến nghị

Đúng như prompt yêu cầu: tỷ lệ lỗi thô (50%) vượt ngưỡng 30%. **Nhưng khuyến nghị của tôi là KHÔNG nên bắt
đầu Phần 1 (router + subagent) ngay**, vì nguyên nhân gốc không phải "agent thiếu tool nhóm nào" như giả
định ban đầu của prompt, mà là:

- 1 bug cụ thể, xác định rõ vị trí, gây ra 4/5 case fail: `_result_vocabulary()` (và các `vocabulary()`
  tương tự trong `impact_tools.py`) cần đưa thêm tên cột (`source_column`, `target_column`,
  `resolved_column`) vào tập từ vựng đã biết trước khi `verify_node` kiểm tra. Sửa 1 chỗ này solo có thể xoá
  gần hết tỷ lệ fail hiện tại.
- 1 khoảng trống dữ liệu (description/RAG coverage) cần điều tra riêng, không liên quan kiến trúc agent.
- Ngân sách tool-call có thể chỉ cần nới nhẹ.

Xây router + 4 subagent song song sẽ tốn thêm độ trễ và độ phức tạp merge/clarify, nhưng **không đụng vào
gốc rễ 3 vấn đề trên** — thậm chí có thể làm bug #1 khó tra hơn vì câu trả lời bị ghép từ nhiều subagent.

Đề xuất thứ tự ưu tiên nếu muốn tiếp tục: (1) sửa bug vocabulary ở `guard.py`/`impact_tools.py`, (2) điều tra
vì sao Q5 search rỗng, (3) chạy lại đúng 10 câu này để đo tỷ lệ fail thật sau khi sửa, (4) chỉ khi tỷ lệ vẫn
≥30% sau khi 2 bug trên đã sửa mới cân nhắc Phần 1.

**Dừng lại ở đây theo đúng yêu cầu — không code tiếp Phần 1.**

## Cập nhật sau khi sửa bug vocabulary (cùng ngày)

Đã sửa đúng phạm vi bug #1 nêu trên, 2 chỗ:

- [`src/agents/tools/impact_tools.py`](../src/agents/tools/impact_tools.py) — `_result_vocabulary()` giờ đưa
  thêm `source_column`/`target_column` của mọi cạnh confirmed/pending, và `resolved_column`, vào tập từ vựng
  đã biết (trước đây chỉ có tên bảng).
- [`src/agents/chat/guard.py`](../src/agents/chat/guard.py) — `unknown_mentions()` nay nhận thêm tham số
  `question` và coi mọi token đã xuất hiện sẵn trong câu hỏi gốc của người dùng là "đã biết" — vì đó không
  thể là điều LLM bịa ra, kể cả khi đó là tên cột/bảng đề xuất mới (đổi tên, thêm cột) chưa từng tồn tại
  trong graph nên không cạnh nào có thể chứng thực được.

Chạy lại đúng 10 câu hỏi cũ (backend restart sạch để chắc chắn nạp code mới):

| # | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Q1 | FAIL (`answer_rejected_unknown_tables`) | **PASS** — trả lời đầy đủ, không warning |
| Q2 | FAIL (`answer_rejected_unknown_tables`) | **PASS** — trả lời đầy đủ (còn `budget_exhausted` nhưng không ảnh hưởng nội dung) |
| Q3 | PASS (nội dung đúng, sai nhóm tool) | PASS — không đổi |
| Q4 | PASS | PASS — không đổi |
| Q5 | FAIL (`answer_rejected_unknown_tables`, che giấu vấn đề thật) | **FAIL vẫn còn, nhưng đúng bản chất**: trả lời trung thực "Không có thông tin nào..." vì `search_by_description`/`search_column_description` trả rỗng — đúng như dự đoán ở mục "Phân loại lỗi" #2, đây là lỗ hổng coverage của RAG mô tả, không phải bug vocabulary, cần điều tra riêng |
| Q6 | PASS | PASS — không đổi |
| Q7 | FAIL (`answer_rejected_unknown_tables`) | **PASS** — trả lời đầy đủ, không warning |
| Q8 | PASS | PASS — không đổi |
| Q9 | PASS (có `budget_exhausted`) | PASS — không đổi |
| Q10 | FAIL (trả lời cụt, bỏ qua DDL preview) | **PASS thực chất** — agent hỏi lại rõ ràng vì có 3 bảng ứng viên khớp tên (`order_items`, `stg_order_items`, `ecom.raw_items`) trước khi preview DDL; đây là hành vi đúng khi tên thật sự mơ hồ, không phải lỗi |

**Kết quả: tỷ lệ fail giảm từ 50% (5/10) xuống 10% (1/10)**, và trường hợp fail còn lại (Q5) đã được xác định
nguyên nhân từ trước (mục #2), không liên quan đến điều phối tool hay bug vocabulary. Toàn bộ test suite liên
quan (`test_chat_guard.py`, `test_chat_capabilities.py`, `test_chat_graph_tools.py`, `test_chat_graph.py`,
`test_ddl_preview_tools.py` — 71 test) vẫn pass sau khi sửa.

Kết luận càng chắc hơn: **không cần Phần 1 (multi-agent)**. Bước tiếp theo hợp lý duy nhất còn lại là điều tra
vì sao `search_by_description`/`search_column_description` trả rỗng cho truy vấn hợp lệ ở Q5 (có thể do
project 787 chưa chạy `describe`/`describe_columns` RAG, hoặc ngưỡng similarity quá chặt) — việc này tách
biệt hoàn toàn khỏi câu hỏi kiến trúc agent.
