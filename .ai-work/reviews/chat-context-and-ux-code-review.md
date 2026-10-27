# Code review — chat-context-and-ux, M-0 → M-3

Ngày 2026-08-30 · reviewer: Claude · phạm vi: `git diff` làm việc trên nền `26b79dc`.
9 file, +143 / −16.

## Kết luận

**Chấp nhận sau khi sửa.** Mã sản phẩm đúng cả bốn mục — tôi đã chạy thật để xác nhận, không chỉ
đọc. Nhưng **hai test end-to-end của M-1 và M-2 không gác được gì**: tôi tắt hẳn cả hai bản sửa
và chúng vẫn xanh. Đó là finding phải sửa trước khi coi M-1/M-2 là xong.

```
$ .venv/bin/pytest -q            621 passed, 60 skipped
$ make lint                      All checks passed!
$ .venv/bin/ruff check eval      All checks passed!
$ diff typecheck-baseline.txt    LECH — nhung khong phai loi cua thay doi nay (F2)
```

## Bám plan

- **Không đụng file cấm.** 9 file đều nằm trong §9. `routes.py`, `query_nodes.py`,
  `storage_service.py`, `session.py`, `state.py` nguyên vẹn — đúng, vì chúng thuộc M-5/M-8.
- `test_search_selection_restarts_original_question_with_the_selected_table_pinned`
  (`:335-356`) **không bị sửa một dòng nào** và vẫn xanh — đúng cổng §8 của M-2.
- Không có refactor lạc, không đổi tên, không bump dependency.

## Đã kiểm từng mục bằng cách chạy, không bằng cách đọc

**M-0 — đạt.** `meta.model` nay đọc được cho **cả năm** report bằng cùng một đường:

```
chat-post-merge-9tool.json       google/gemini-3.5-flash-lite
chat-post-merge-baseline.json    openai/gpt-4.1-mini
chat-post-merge-content.json     google/gemini-3.5-flash-lite
chat-post-merge-gemini.json      google/gemini-3.5-flash-lite
chat-post-merge-language.json    google/gemini-3.5-flash-lite   <- truoc M-0: None
```

`meta.timestamp = 2026-08-29T03:48:49.172490+00:00` **khớp đúng** mốc trace mà plan §M-0 chỉ ra,
không phải mốc tự đặt. Comment `registry.py:20` đã ghi phạm vi đo thật (db 1, 2, 2363).

**M-1 — mã chạy đúng.** Chạy lại đúng kịch bản D1 trên db 1:

```
T1 'revenue_alert có gì?'      -> clarification, options=[overtime_alerts, revenue_alerts_final,
                                                          revenue_alerts_staging]
T2 'revenue_alerts_staging'    -> steps=[traverse(downstream, revenue_alerts_staging),
                                         traverse(upstream, revenue_alerts_staging)]
                                  TRA: "Bảng `revenue_alerts_staging` chuẩn bị và dàn dựng dữ liệu..."
```

Trước M-1, chính lượt T2 này trả *"Không tìm thấy bảng `revenue_alert`, tuy nhiên đã phát hiện
bảng liên quan…"*. Regex biên identifier (`chat_service.py:38-41`) đúng hợp đồng C-1, và
`resumed_question` được dùng cho **cả** `question` lẫn `HumanMessage` (`:262-267`) — đúng.

**M-2 — đúng hợp đồng C-2.** `resolve.py:155-174` xét đúng thứ tự đã chốt, và test đơn vị của nó
**thật sự gác**: tắt bản sửa → `test_chat_resolve.py:74` đỏ ngay.

**M-3 — đúng hợp đồng C-3, và test gác thật.** `impact_tools.py:100-101` chỉ thử lại khi
`params.column` là cột **có thật**. Tắt nhánh này (ép `is_known_column` trả `False`) thì 2/3 test
mới đỏ — nghĩa là chúng đo hành vi thật, không đo chính kịch bản của mình. Ca âm
(`table="*"` + cột không có thật → vẫn `table_not_found`, `mention="*"`) xanh ở cả hai chiều,
đúng bản chất một ca âm.

---

## F-1 — **Major.** Hai test end-to-end của M-1 và M-2 không gác được gì

`tests/test_api/test_chat_routes.py:360-380` và `:383-402`.

**Bằng chứng.** Tôi tắt hẳn cả hai bản sửa bằng một plugin pytest (không sửa file nào trong repo):
`match_clarification` trả về hành vi cũ, `_question_with_choice` thành hàm đồng nhất. Kết quả:

```
$ pytest tests/test_api/test_chat_routes.py -p revert_plugin \
         -k "rewrites_the_original_question or does_not_resume_the_old_question"
2 passed
```

Hai test được viết ra để bắt D1 và D2 vẫn xanh khi D1 và D2 quay lại nguyên vẹn.

**Vì sao.** `FakeLLM.invoke(self, _messages)` (`:115`) **bỏ qua** messages, và `set_llms` (`:167`)
mặc định compose trả đúng chuỗi `"answer"`. Nên mọi khẳng định đang đọc lại chính thứ test tự
viết ra:

| Dòng | Khẳng định | Vì sao vô hiệu |
| --- | --- | --- |
| `:378` | `steps[0]["args"]["query"] == "revenue_alerts_staging"` | đó là câu trả lời **thứ hai đã kịch bản hoá**, không phải bằng chứng câu hỏi được viết lại |
| `:380` | `"revenue_alert" not in answer` | `answer` là chuỗi literal `"answer"` |
| `:401` | `steps[0]["args"]["table"] == "revenue_alerts_staging"` | cũng là kịch bản |
| `:402` | `agent.calls == 3` | nhánh bị cướp lượt **cũng** invoke graph → cũng đúng 3 |

**Vì sao quan trọng.** Đây là hai lỗi mà cả milestone sinh ra để sửa. Xoá `_question_with_choice`
hoặc revert `match_clarification`, CI vẫn xanh. Plan §5 đòi đúng chỗ này: *"khẳng định câu hỏi đi
vào graph ở lượt resume mang tên đã chọn"* và *"chứng minh câu mới thật sự qua agent"*.

**Sửa.** Cho `FakeLLM` nhớ messages rồi khẳng định trên thứ agent **nhận được**:

```python
class FakeLLM:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0
        self.seen: list[list] = []      # them

    def invoke(self, messages):
        self.calls += 1
        self.seen.append(messages)      # them
        return next(self.responses)
```

- D1 (`:378-380`): `human = agent.seen[-1][-1].content` → `assert "revenue_alerts_staging" in human`
  **và** `assert "revenue_alert có gì" not in human`.
- D2 (`:401-402`): `assert agent.seen[-1][-1].content == "revenue_alerts_staging ảnh hưởng tới những bảng nào vậy nhỉ"`.

Cả hai nằm trong file §9 đã cho phép. Sau khi sửa, chạy lại với plugin tắt-bản-sửa: **phải đỏ**.
Nếu vẫn xanh thì test vẫn chưa gác.

## F-2 — **Minor.** Cổng typecheck của plan đã lỗi thời sau merge — không phải lỗi của thay đổi này

`diff eval/results/typecheck-baseline.txt` **không rỗng** (24 → 27 dòng), nên cổng §6 như đang
viết không thể xanh. Nhưng lỗi lệch **không** thuộc thay đổi này:

```
schemas.py, graph_service.py, llm_extraction_service.py, parser_service.py
  -> ca 4 file deu KHONG nam trong git diff cua M-0..M-3
grep 4 file Codex sua (chat_service, chat/resolve, impact_tools, chat/registry) trong output mypy
  -> KHONG co loi nao
```

Mốc được sinh trước merge `26b79dc`; merge mang về `parser_service`/`llm_extraction_service` mới
nên số lỗi nền đổi.

**Vì sao quan trọng.** Cổng đang đỏ vì lý do ngoài phạm vi thì lần sau người chạy sẽ quen tay bỏ
qua nó, và một hồi quy thật sẽ lọt.

**Sửa** (cần người ra đề đồng ý, vì `typecheck-baseline.txt` nằm trong §10 cấm sửa): sinh lại mốc
đúng một lần bằng lệnh đã ghi trong plan, kèm một dòng ghi rõ mốc đổi vì merge `26b79dc`, không
phải vì M-0..M-3:

```sh
.venv/bin/mypy src 2>&1 | grep "error:" | sed 's/: error.*//' | sort \
  > eval/results/typecheck-baseline.txt
```

## Nit — không phải finding

`chat-post-merge-language.json` giữ `runs_per_question` ở gốc trong khi các report anh em để
`runs_per_case` trong `meta`. Plan không đòi chuyển, để nguyên cũng được; chỉ ghi lại cho ai sau
này gộp số liệu khỏi ngạc nhiên.

## Việc tiếp theo

1. Sửa F-1 (một thay đổi nhỏ trong file test đã được phép).
2. Hỏi người ra đề về F-2 trước khi chạm `typecheck-baseline.txt`.
3. Rồi mới sang **M-4** — và nhớ kỷ luật của M-4: **chỉ đo, không sửa mã**.

---

# Code review — M-4, M-5

Ngày 2026-08-30 · phạm vi: `git diff` làm việc + 2 report eval mới + 2 case mới.

## Kết luận

**Chấp nhận về mã, nhưng còn hai việc treo.** M-5 đạt đúng mục đích nó sinh ra — tôi đọc câu trả
lời thật chứ không chỉ nhìn pass/fail, và chúng đã thành **giả thuyết có neo vào fact** thay vì
liệt kê bảng. Hai việc treo: **F-1 của đợt trước chưa sửa**, và cổng "8 case cũ" của M-5 không
đạt — nhưng lỗi nằm ở **cổng do tôi viết**, không phải ở mã (F-4).

```
$ .venv/bin/pytest -q            625 passed, 60 skipped   (truoc M-4/M-5: 621)
$ make lint                      All checks passed!
$ .venv/bin/ruff check eval      All checks passed!
```

## M-4 — đạt, và kỷ luật "chỉ đo, không sửa" giữ được

```
before: model=gemini-3.5-flash-lite  rev=26b79dc  runs/case=3  30 luot  api_error=0
after : model=gemini-3.5-flash-lite  rev=26b79dc  runs/case=3  30 luot  api_error=0
timestamp: before 03:06:26Z  ->  after 03:13:54Z
```

Hai case mới khớp **từng chữ** hợp đồng C-4. Và có bằng chứng lượt `before` thật sự chạy **trước**
khi sửa prompt, không phải chạy lại sau cho đẹp: case 10 ở `before` gọi `['traverse']` 2/3 lượt
(thiếu `breaking_changes`) — đúng hành vi của luật cũ; sau M-5 mới thành `breaking_changes →
traverse`. Đây chính là số đo trả lời câu hỏi *"orchestration đã chuẩn chưa"*: **chưa**, và nay đã.

## M-5 — đạt mục đích, đo được

| Case | before | after |
| --- | --- | --- |
| 10 `high_risk_claim` | tool **1/3** (`missing_tools: breaking_changes`) | tool **3/3**, cả 3 lượt `breaking_changes → traverse` |
| 11 `abnormal_lab_count` | tool 3/3 | tool 3/3 |

Quan trọng hơn con số: **câu trả lời đã đổi chất**. Đọc từ `logs/chat-traces/2026-08-30.jsonl`:

> *Nguyên nhân tiềm ẩn thứ nhất: Biểu thức chuyển đổi `CASE WHEN claim_status = 'denied' THEN TRUE
> ELSE FALSE END` tại `insurance_risk_alerts.high_risk_claim` có thể không phản ánh đúng logic
> nghiệp vụ… Nguyên nhân tiềm ẩn thứ hai: Cột `claim_status` từ bảng upstream
> `insurance_claims_summary`… Lưu ý: Các nguyên nhân trên là các giả thuyết cần được kiểm chứng.*

> *Biểu thức tính toán `COUNT(CASE WHEN labs.is_abnormal THEN 1 END)` tại dòng 12… Nguồn dữ liệu
> thượng nguồn `raw_lab_results.is_abnormal` truyền qua `stg_lab_results.is_abnormal`…*

Đủ cả ba điều kiện §8: xếp hạng, mỗi nguyên nhân neo vào một fact cụ thể có tên `bảng.cột`, và
nói rõ là giả thuyết. Không còn kiểu "đây là danh sách bảng, bạn tự kiểm".

Bốn test mới trong `test_chat_graph.py` **gác thật**: chúng bắt `compose_llm.messages[0].content`,
khẳng định cả nội dung lẫn **thứ tự** luật, cộng một test wiring kiểm `breaking_changes_checked`
và biểu thức `CASE WHEN` đi tới được facts. Xoá khối prompt là đỏ.

## F-3 — **Major, lặp lại.** F-1 chưa được sửa

`tests/test_api/test_chat_routes.py:115` vẫn là `def invoke(self, _messages)`, không có `self.seen`.
Chạy lại đúng phép thử cũ:

```
$ pytest tests/test_api/test_chat_routes.py -p revert_plugin \
         -k "rewrites_the_original_question or does_not_resume_the_old_question"
2 passed          <- van xanh khi M-1 va M-2 bi tat han
```

Hai lỗi trọng tâm của M-1/M-2 vẫn không có cổng nào gác. Cách sửa đã ghi nguyên văn ở F-1; nó nằm
trong file test đã được §9 cho phép và chỉ là ba dòng.

## F-4 — **Major, nhưng lỗi ở cổng tôi viết, không phải ở mã**

Cổng §8 của M-5 đòi: *8 case cũ, `tool_micro_average`/`content_micro_average` **không thấp hơn**
`chat-post-merge-content.json` (1.000/1.000)*. Tính riêng trên 8 case cũ:

```
chat-post-merge-content.json (moc trong plan) : 1.000 / 1.000   <- do o 42cd08a, TRUOC merge
chat-context-and-ux-before.json               : 0.958 / 0.958   <- da thap hon, TRUOC khi M-5 sua gi
chat-context-and-ux-after.json                : 0.917 / 0.917
```

Mốc trong plan đo ở **một trạng thái mã khác** (`42cd08a`, trước khi merge `26b79dc` mang về
`parser_service`/`impact_service` mới). Trên nhánh này, 8 case cũ **chưa bao giờ** ở 1.000 —
`before` đã 0.958 khi chưa ai đụng tới M-5. Cổng vì thế không đo được cái nó định đo. Đây là lỗi
của tôi lúc viết plan.

Còn chênh lệch thật giữa `before` và `after` (cùng nền mã) là **đúng một lượt** của case 07:
23/24 → 22/24, ở N=3.

**Tôi đã thử quy trách nhiệm và thất bại — nên không được sửa prompt theo linh cảm.** Chạy A/B
riêng case 07, 5 lượt mỗi bên:

```
lan 1:  LUAT MOI 2/5   |  LUAT CU 5/5      <- trong nhu bang chung
lan 2 (dao thu tu):  LUAT CU 4/5  |  LUAT MOI 5/5   <- nguoc han lai
```

Hai lượt A/B **mâu thuẫn nhau**. Gộp cả số của eval thì luật cũ 11/13, luật mới 8/13 — chênh
nhưng không đủ để kết luận ở cỡ mẫu này. **Không có bằng chứng M-5 làm hỏng case 07.**

Cơ chế hỏng của case 07 giống hệt nhau ở cả hai điều kiện, và nó mới là thứ đáng ghi: agent gọi
`search_tables`, nhận về nhiều ứng viên → `stop_reason=clarification` → lượt kết thúc với **1 lời
gọi tool**, không bao giờ tới `traverse`. Content trượt theo là hệ quả (không có bằng chứng để
trích), không phải một lỗi nội dung riêng.

**Đề xuất, theo thứ tự:**

1. Sửa **cổng** trong plan §8: so `after` với `before` **cùng nền mã**, không so với
   `chat-post-merge-content.json` đo ở `42cd08a`. Cần người ra đề duyệt vì plan đã approved.
2. **Không** đụng prompt để "chữa" case 07 — dữ liệu không đỡ được quyết định đó, và plan cấm
   nới `must_contain`/`max_calls` cho vừa kết quả.
3. Nếu người ra đề muốn biết chắc case 07 ổn định tới đâu: chạy riêng nó với N lớn (≥15), một lần,
   rồi mới quyết. Đây là câu hỏi về độ ổn định của case, không phải về M-5.

## Việc tiếp theo

1. F-3 (ba dòng trong file test đã cho phép) — bắt buộc trước khi coi M-1/M-2 là xong.
2. Người ra đề quyết F-4 và F-2 (mốc typecheck).
3. Rồi mới sang M-6.

---

# Code review — bản sửa F-3

Ngày 2026-08-30 · phạm vi: `tests/test_api/test_chat_routes.py` (+6 dòng so với đợt trước).

## Kết luận

**F-3 đóng.** Hai test nay gác thật, và gác **đúng lỗi của mình** chứ không gác chung chung.

`FakeLLM` (`:110-119`) giờ nhớ messages (`self.seen`), và mỗi test khẳng định trên **câu hỏi mà
agent thực sự nhận**:

```python
assert agent.seen[1][-1].content == "revenue_alerts_staging có gì?"                      # D1
assert agent.seen[1][-1].content == "revenue_alerts_staging ảnh hưởng tới những bảng nào vậy nhỉ"  # D2
```

Đây đúng chỗ trước kia rỗng: giá trị này do **mã** sinh ra, không phải do kịch bản test tự viết.

## Kiểm bằng cách tắt từng bản sửa một

```
tat CA HAI (M-1 + M-2)  -> 2 failed      (truoc khi sua F-3: 2 passed)
tat RIENG M-1           -> D1 do, D2 xanh
tat RIENG M-2           -> D2 do, D1 xanh
```

Không có chéo nhau: mỗi test đỏ đúng khi lỗi của chính nó quay lại, và im lặng với lỗi kia. Đây
là điều kiện tôi đặt ra ở F-1 (*"chạy lại với plugin tắt-bản-sửa: phải đỏ"*) — nay đạt.

```
$ .venv/bin/pytest -q            625 passed, 60 skipped
$ make lint                      All checks passed!
$ .venv/bin/ruff check eval      All checks passed!
```

## Trạng thái

| Mục | Trạng thái |
| --- | --- |
| M-0, M-1, M-2, M-3 | **xong** — mã đúng, test gác thật |
| M-4, M-5 | **xong** — orchestration case 10 từ 1/3 lên 3/3, câu trả lời thành giả thuyết có neo fact |
| F-2 (mốc typecheck lệch do merge) | **chờ người ra đề** — cần đồng ý mới được sinh lại `typecheck-baseline.txt` (§10 cấm) |
| F-4 (cổng "8 case cũ ≥ 1.000" so sai mốc) | **chờ người ra đề** — sửa cổng trong plan §8, và **không** đụng prompt để chữa case 07 |

Sẵn sàng sang **M-6**.

---

# Code review — M-6, M-7

Ngày 2026-08-30 · phạm vi: `git diff frontend/` + 6 file mới trong `frontend/src/utils/`.

## Kết luận

**Chấp nhận.** Không có finding chặn. Hai điều đáng ghi: một quan sát đo được về **giá phải trả
của chính hợp đồng C-5** (F-5), và phần nghiệm thu tay trong app **tôi chưa chạy** — nói rõ để
không ai tưởng nó đã được kiểm.

```
$ cd frontend && npm test        4 files, 16 tests passed
$ npm run typecheck              sach
$ grep "stg_orders|fct_daily_sales_revenue|Tableau" FloatingChatbot.tsx   -> rong (cong §8)
$ .venv/bin/pytest -q            625 passed, 60 skipped   (khong hoi quy backend)
```

## Bám plan

- Chỉ `App.tsx` và `FloatingChatbot.tsx` bị sửa, cộng 3 util + 3 test mới — đúng §9.
  **`frontend/src/types/backend.ts` không bị đụng**, đúng §10: M-6 rút gọn nên không cần
  `stop_reason` nữa, và Codex không thêm nó "cho chắc".
- `App.tsx` derive **một lần** `realNodes`/`realTables` từ `graphResponseToLineageData(realGraphCtx.data)`
  — **không** lấy từ state `nodes` (vốn trộn mock khi `SHOW_MOCK_DEMO_DATA` bật). Đúng C-5, và
  M-7 dùng lại prop đó chứ không sửa `App.tsx` lần hai.

## R7 và R9 — hai chỗ review vòng trước bắt được, nay đúng

**R7 (graph rỗng):** `buildSuggestions([])` trả `[]`, và component rẽ nhánh
`suggestions.length > 0 ? <button…> : <p…>`. Mảng rỗng ra **một dòng chữ tĩnh**, không nút, không
nhãn "Thử hỏi:" — không còn chuyện bấm vào rồi gửi chính câu thông báo đi hỏi.

**R9 (giữ chat mở):** nút entity gọi **đúng một việc**:

```tsx
onClick={() => onNavigateToNode(chunk.nodeId)}
```

Tôi soi cả file: 5 chỗ còn `setIsOpen(false)` đều là chỗ cũ, không liên quan — nút đóng (`:229`),
khối "Tài sản dữ liệu liên quan" (`:292`, plan cho phép giữ nguyên), và 3 phím tắt
(`:390/:399/:408`). Nút entity **không** nằm trong số đó.

**Gợi ý câu hỏi tiếp theo đã gỡ đúng cách:** `suggestedQueries: data.clarification_options || []`
(bỏ `data.suggestions`), nhãn đổi thành "Chọn một bảng:", và bấm vẫn gửi **tên trần** — đúng hình
dạng lựa chọn mà M-2 mới siết. Ba khối hardcode ở lời chào / reset / fallback đã biến mất.

## `linkifyEntities` — kiểm kỹ phần dễ sai

- Ưu tiên tên dài: sort giảm dần theo độ dài **trước** khi dựng `Map`, mà `Map` giữ thứ tự chèn,
  nên nhánh alternation của regex đúng thứ tự dài→ngắn. `revenue_alerts_final` không bị
  `revenue_alerts` cắt — test khẳng định đúng chỗ này.
- Biên identifier `(?<![A-Za-z0-9_.])…(?![A-Za-z0-9_.])`: dấu `.` nằm trong character class nên là
  ký tự thường, không phải "ký tự bất kỳ". `revenue_alerts_finalized` không khớp — có test.
- `escapeRegex` cho tên bảng, nên tên có ký tự đặc biệt không phá regex.

## F-5 — **Observation, không phải lỗi của bản cài đặt.** Chỉ 5/35 tên cột bấm được

Đo trên đồ thị thật của db 1:

```
36 bang | 35 ten cot khac nhau | cot bam duoc (duy nhat toan do thi): 5
bam duoc     : abnormal_count, high_risk_claim, last_discharge_at, occupied_beds, segment
KHONG bam duoc: abnormal_lab_count, amount_paid, appointment_count, claim_status, patient_id, ...
```

Codex cài đúng hợp đồng C-5 (*"chỉ giữ cột có tên duy nhất toàn đồ thị"*) — **hợp đồng đó là của
tôi**, và đây là giá của nó: đúng những cột mà chat hay nói tới nhất — `claim_status`,
`abnormal_lab_count`, `amount_paid`, `appointment_count` — đều trùng tên ở ≥2 bảng nên **không**
bấm được. Nửa "bấm tên cột" của M-7 gần như im lặng trên dữ liệu thật; nửa "bấm tên bảng" chạy đủ.

**Người ra đề quyết, hai đường:**

1. **Chấp nhận** — tên bảng mới là thứ hay bấm, cột để sau. Không tốn gì thêm.
2. **Nới quy tắc**: với cột trùng tên, gắn nó vào bảng được nhắc **gần nhất phía trước** trong
   cùng câu trả lời (câu trả lời thật đang viết đúng dạng *"cột `abnormal_lab_count` trong bảng
   `patient_risk_score`"*, nên tín hiệu có sẵn). Đây là **đổi hợp đồng C-5**, cần duyệt lại, và
   phải kèm test cho ca "không có bảng nào phía trước → không bấm được".

## Nit — không chặn

- `buildSuggestions` sort bằng `localeCompare`, tức phụ thuộc locale của runtime. Tên bảng đều
  ASCII nên hiện không lộ; dùng so sánh thuần sẽ tất định hơn.
- `realNodes` chỉ lấy từ `GET /graph`, **không** gồm node sinh từ cạnh pending
  (`pendingEdgesToLineageData`), trong khi backend `known_tables()` có tính cạnh pending. Một bảng
  chỉ tồn tại qua cạnh pending sẽ được chat gọi tên nhưng không bấm được. Đúng tinh thần "chỉ đồ
  thị thật", ghi lại để sau khỏi tưởng là lỗi.

## Tôi chưa kiểm phần nào

**Chưa chạy app.** Ba khẳng định của §8 phải nghiệm thu tay và tôi không thực hiện: bấm tên bảng
thì Explorer chọn đúng node; popup **vẫn mở** với nguyên vị trí cuộn; bấm được tên thứ hai ngay
sau đó. Mã đọc thì đúng cả ba, nhưng đọc mã không thay được một lần bấm thật.

## Trạng thái

M-0 → M-7 xong. Còn treo, đều chờ người ra đề: **F-2** (mốc typecheck — chỉ thật sự cần trước
M-8), **F-4** (sửa cổng "8 case cũ" trong plan §8), và **F-5** ở trên. Sẵn sàng sang **M-8**.

---

# Code review — M-8 (streaming)

Ngày 2026-08-30 · phạm vi: `git diff` + 2 file util mới (`sseParser.ts`, `chatSteps.ts`).

## Kết luận

**Phải sửa rồi review lại — có một blocker.** Lớp streaming **mất bước ở mọi câu hỏi cần từ hai
vòng tool trở lên**, và vì `answer_question` nay tiêu thụ chính lõi đó, **`POST /chat` cũng hồi
quy theo** — không chỉ SSE. Cụ thể: case 10, cái mà M-5 vừa kéo từ 1/3 lên 3/3, nay trả về
`tools_called = ['traverse']`, tức mất `breaking_changes`, tức **về lại 0/3** nếu chạy eval.

Ba việc còn thiếu: lượt eval bắt buộc sau M-8, toàn bộ test của M-8, và một lỗi mypy mới.

```
$ .venv/bin/pytest -q      625 passed, 60 skipped   (KHONG tang — khong co test M-8 nao)
$ make lint                All checks passed!
$ cd frontend && npm test  16 passed              (KHONG tang — thieu 2 file test)
$ cong mypy §6             DO — 2 loi moi (F-9)
```

## F-6 — **Blocker.** Mất bước ở câu hỏi nhiều vòng tool; `POST /chat` hồi quy theo

**Bằng chứng 1 — kịch bản dựng sẵn hai vòng tool, so đường cũ với đường mới:**

```
invoke()  -> steps=2  tools=['traverse','traverse']  confirmed=2
stream()  -> su kien "step" phat ra = 1
          -> done.steps=1  tools=['traverse']  confirmed=1
```

**Bằng chứng 2 — chạy thật case 10 sau M-8:**

```
steps tra ve   : [('traverse', agent_step=2)]
tool_calls_used: 2          <- dem thi dung 2
confirmed      : 3
=> eval doc must_call tu day: tools_called = ['traverse']   <- mat breaking_changes
```

`tool_calls_used` vẫn đúng nên nhìn thoáng qua tưởng không sao; chính `steps` và `confirmed` mới
bị mất.

**Hai nguyên nhân độc lập, phải sửa cả hai.**

**(a) `src/services/chat_service.py` — cắt lát sai đối tượng:**

```python
for step in _steps({"steps": update.get("steps", [])})[emitted_steps:]:
```

`update["steps"]` là **delta của riêng vòng đó**, nhưng `emitted_steps` là **tổng luỹ kế**. Vòng 1
có 1 bước → `emitted_steps = 1`. Vòng 2 cũng có 1 bước → `[1:]` → **rỗng** → không phát sự kiện
`step` nào nữa. Càng nhiều vòng càng mất.

**(b) `state.update(update)` — ghi đè đúng những khoá mà LangGraph gộp bằng reducer.**
`ChatAgentState` khai `steps: Annotated[list, operator.add]`, `confirmed`/`pending` dùng
`dedupe_edges`, `vocabulary` dùng `operator.or_`, `warnings` dùng `operator.add`, `messages` dùng
`add_messages` (`src/agents/state.py:50-74`). `dict.update` là **ghi đè phẳng**, nên state cuối chỉ
còn dữ liệu của **vòng cuối**. Trước đây `invoke()` trả state đã gộp sẵn nên không ai phải nghĩ tới
chuyện này.

Hệ quả không dừng ở hiển thị: `confirmed` là **fact đưa vào câu trả lời**, nên câu trả lời cũng
nghèo đi. Và `vocabulary` bị ghi đè có thể làm `verify_node` báo nhầm tên bảng "không xác thực".

**Sửa (đề xuất):** đổi sang `stream_mode=["values", "messages"]`. Chế độ `values` trả **nguyên
state đã gộp** sau mỗi node, nên:

```python
if mode == "values":
    state = payload                      # khong tu gop nua, khong dung reducer bang tay
    steps = _steps({"steps": state.get("steps", [])})
    for step in steps[emitted_steps:]:   # gio moi dung: cat lat tren danh sach LUY KE
        yield {"event": "step", "data": step}
    emitted_steps = len(steps)
```

Một thay đổi sửa **cả hai** nguyên nhân. Nếu vì lý do nào đó phải giữ `updates`, thì bắt buộc gộp
bằng đúng reducer của từng khoá — đừng dùng `dict.update`.

**Cổng phải thêm cùng lúc:** một test hai vòng tool, khẳng định `done.steps` có **đủ 2** bước và
số sự kiện `step` bằng 2. Không có test đó thì lỗi này sẽ quay lại lặng lẽ.

## F-7 — **Major.** Lượt eval bắt buộc sau M-8 không được chạy

`eval/results/chat-context-and-ux-stream.json` **không tồn tại**. §6 ghi rõ: *"Sau M-8, chạy lại
eval một lượt vì `compose_node` đã đổi cách gọi LLM… không được tụt"*. Đây không phải thủ tục cho
đẹp — chính lượt đó sẽ bắt được F-6: case 10 mất `breaking_changes` là `must_call` trượt ngay,
`tool_micro_average` tụt thấy rõ.

**Sửa:** sửa F-6 trước, rồi mới chạy; chạy trước khi sửa chỉ tốn tiền để đo một bản đã hỏng.

## F-8 — **Major.** Không có test nào cho M-8

`pytest` vẫn **625** (y hệt trước M-8) và `vitest` vẫn **16**. §5 liệt kê **sáu** hàng test cho
M-8, không hàng nào tồn tại:

| Cần có (§5) | Trạng thái |
| --- | --- |
| `/chat/stream` phát đúng thứ tự `step*` → `token*` → `done`, `done` khớp `POST /chat` | **thiếu** |
| 3 chunk compose → **3** sự kiện `token` riêng biệt trước `done` | **thiếu** |
| `ToolMessage` của node `tools` không lọt ra thành `token` | **thiếu** |
| `chat_verify_mode="replace"` → không có `token` nào | **thiếu** |
| R11/R13: đóng iterator sớm → không turn/clarification/trace, session row rỗng | **thiếu** |
| `compose_node` dùng `.stream()`: 3 chunk → answer ghép đủ; lỗi → `_template_answer` | **thiếu** |
| `sseParser.test.ts`, `chatSteps.test.ts` | **thiếu** (`sseParser.ts` và `chatSteps.ts` đã có) |

Thay đổi duy nhất trong `test_chat_routes.py` là thêm `stream()` và `seen` cho `FakeLLM` — cần
thiết vì compose nay stream, và **không** đụng nội dung test cũ nào, đúng cổng §2.0. Nhưng đó là
sửa hạ tầng test, không phải test mới.

## F-9 — **Major.** Cổng mypy §6 đỏ ngay lần chạy đầu

```
src/services/chat_service.py: error: Argument 4 to "_initial_chat_state" has incompatible type
                              "str | None"; expected "str"  [arg-type]   (x2)
```

`_initial_chat_state(..., last_table: str)` nhưng `_last_resolved_table()` trả `str | None`.
**Sửa:** khai `last_table: str | None`. *(Ghi nhận: cổng fail-closed mới thêm ở vòng plan trước
đã bắt được lỗi thật ngay lần dùng đầu tiên.)*

## Những chỗ làm đúng, đáng ghi

- **Cái bẫy tôi cảnh báo đã được chặn:** `token` chỉ phát khi
  `metadata["langgraph_node"] == "compose"`, nên JSON thô của node `tools` không lọt vào bong bóng
  chat. Kèm điều kiện `chat_verify_mode == "warn"` đúng ràng buộc §2.7.
- **R11/R13 đúng thứ tự:** `set_clarification` → `_write_trace` → `save_turn` đều nằm **ngay
  trước** `yield done`; ngắt sớm là không chạy tới. (Chưa có test, xem F-8.)
- **`sseParser.ts` đúng hợp đồng R12:** một `TextDecoder` với `{stream: true}` dùng chung, `buffer`
  xuyên các lần đọc, tách theo `\r?\n\r?\n`, gom nhiều dòng `data:` bằng `\n`, khung hỏng thì bỏ
  qua chứ không ném; `done`/`error` → `reader.cancel()`.
- **`routes.py` chỉ thêm `/chat/stream`**, `POST /chat` không đụng một dòng; có
  `ensure_database_role`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- **`thought` lọc đúng:** rỗng hoặc `DONE` thì không phát — đúng "best-effort, không bịa".

## Việc tiếp theo, theo thứ tự

1. **F-6** — đổi sang `stream_mode=["values","messages"]`, kèm test hai vòng tool.
2. **F-9** — một dòng chữ ký kiểu.
3. **F-8** — viết đủ test M-8; ít nhất test hai vòng tool và test `verify_mode=replace` phải có.
4. **F-7** — chạy `chat-context-and-ux-stream.json` **sau** khi ba việc trên xong.

---

# Code review — bản sửa M-8 (vòng 1)

Ngày 2026-08-30.

## Kết luận

**F-6 và F-9 đóng, kiểm bằng số.** F-8 mới xong một nửa (chỉ frontend, và một test không gác được
cái nó tưởng đang gác), F-7 chưa làm. **Chưa xong M-8.**

```
$ .venv/bin/pytest -q            625 passed, 60 skipped   (VAN khong tang — F-8)
$ make lint                      All checks passed!
$ cong mypy §6                   DAT
$ cd frontend && npm test        6 files, 18 tests        (them sseParser + chatSteps)
$ npm run typecheck              sach
```

## F-6 — **đóng.** Đổi sang `stream_mode=["values","messages"]` là đúng thuốc

`state = payload` (state đã gộp sẵn bởi reducer) + cắt lát trên **danh sách luỹ kế**. Chạy lại
đúng hai phép đo đã tố cáo lỗi:

```
kich ban 2 vong tool:
  invoke()  -> steps=2  confirmed=2
  stream()  -> su kien step = 2 | done.steps=2 tools=['traverse','traverse'] confirmed=2   <- khop het

case 10 that:
  tools_called = ['breaking_changes', 'traverse']   <- truoc ban sua: ['traverse']
  calls = 2 | confirmed = 3
```

`emitted_thoughts` cũng đếm theo `len(messages)` luỹ kế và có `isinstance(message, AIMessage)` nên
`ToolMessage` không lọt ra thành `thought`. Đúng.

## F-9 — **đóng.** `last_table: str | None`, cổng mypy §6 xanh trở lại

## F-7 — **còn nguyên.** Chưa có `eval/results/chat-context-and-ux-stream.json`

Giờ mới là lúc chạy được: F-6 đã sửa nên số đo sẽ nói về bản đúng.

## F-8 — **còn một nửa, và phần thiếu là phần quan trọng nhất**

**Backend: vẫn không có một test nào.** `grep -rl "chat/stream\|answer_question_stream" tests/` →
**không có file nào**. `pytest` vẫn đúng **625**. Nghĩa là:

- không test nào chạm `POST /chat/stream`;
- không test nào khẳng định thứ tự `step*` → `token*` → `done`;
- không test `chat_verify_mode="replace"` → không `token`;
- không test R11/R13 (ngắt sớm → không turn/clarification/trace, session row rỗng);
- **và không test nào gác chính F-6.** Bản sửa vừa rồi hiện chỉ được chứng minh bằng **probe của
  tôi**, không phải bằng cổng trong repo. Ai đó đổi lại `stream_mode` thành `"updates"` là lỗi quay
  về nguyên vẹn, CI vẫn xanh.

Test tối thiểu phải có, và tôi đã nêu ở lượt trước: kịch bản **hai vòng tool** bằng `FakeLLM`,
khẳng định số sự kiện `step` bằng **2** *và* `done.steps` có **2** phần tử.

**`sseParser.test.ts` không kiểm được thứ R12 sinh ra để chặn.** Test đang cắt khung **trong
chuỗi JavaScript**:

```js
feedSse("", 'event: token\ndata: {"text":"lấy')      // cat o ranh gioi KY TU
```

Nhưng `TextDecoder` **không tham gia** vào `feedSse` — nó nằm ở `askChatStream`. Lỗi R12 mô tả là
cắt ở ranh giới **byte**, và nó chỉ hiện ra khi decode:

```
cat trong chuoi   -> ghep lai nguyen ven (decoder khong tham gia)
cat theo byte 30  -> {"text":"l���y dữ liệu"}        <- day moi la loi that
```

Nên test hiện tại **vẫn xanh kể cả khi bỏ `{stream: true}`** khỏi decoder. Plan §5 ghi rõ ca cần
có: `TextEncoder` khung đó, cắt ở **byte 30** (giữa chữ `ấ`), decode hai mảnh bằng **một**
`TextDecoder` `{stream: true}`, rồi mới đưa vào `feedSse`, và khẳng định không có `�`.

`chatSteps.test.ts` thì mỏng nhưng đúng hướng: mới 2 khẳng định, thiếu ca `traverse` không có
`column` và ca tool lạ — cứ để lại cũng được, không chặn.

## Việc tiếp theo

1. Test hai vòng tool cho `/chat/stream` (gác F-6) — **bắt buộc**, đây là lỗ hổng đáng lo nhất.
2. Test byte-split cho decoder (gác R12), cộng các test M-8 còn thiếu ở §5.
3. Rồi mới chạy `chat-context-and-ux-stream.json` (F-7).

---

# Code review — bản sửa M-8 (vòng 2)

Ngày 2026-08-30.

## Kết luận

**F-6, F-8, F-9 đóng; F-7 đã chạy.** Nhưng chính lượt eval bắt buộc đó lộ ra một hồi quy mới —
và lần này tôi **đo được nguyên nhân**, khác với case 07 hồi trước: **luật "kể lý do chọn tool"
của M-8 (bước 22b) làm hỏng case 03**. Đây là finding phải quyết trước khi chốt M-8.

```
$ .venv/bin/pytest -q       626 passed, 60 skipped   (+1: test hai vong tool)
$ npm test                  6 files, 19 tests
$ cong mypy §6              DAT
```

## F-6 — **đóng, và nay có cổng gác thật**

`test_chat_stream_keeps_every_step_across_two_tool_rounds` khẳng định đúng ba thứ tôi đòi: 2 sự
kiện `step`, `done.steps` có 2 phần tử, `confirmed` = 2. Tôi kiểm nó có **đỏ khi lỗi quay lại**
bằng cách bọc `build_chat_graph` để phát delta của từng node nhưng gắn nhãn `values` — tức dựng
lại đúng lỗ hổng cũ:

```
$ pytest -p old_stream -k keeps_every_step_across_two_tool_rounds
FAILED tests/test_api/test_chat_routes.py::test_chat_stream_keeps_every_step_across_two_tool_rounds
```

Gác thật, không phải gác hình thức.

## F-8 — **đóng phần trọng yếu.** `sseParser.test.ts` nay kiểm đúng ranh giới **byte**

```js
const bytes = new TextEncoder().encode('event: token\ndata: {"text":"lấy dữ liệu từ đâu"}\n\n');
decoder.decode(bytes.slice(0, 30), { stream: true }) + decoder.decode(bytes.slice(30), { stream: true })
```

Cắt ở **byte 30** (giữa chữ `ấ`) và decode bằng **một** `TextDecoder` — bỏ `{stream: true}` là
`JSON.parse` chết, tức test đỏ. Đúng thứ R12 sinh ra để chặn.

Vẫn còn thiếu vài hàng §5 (`verify_mode="replace"` → không `token`; ToolMessage không lọt thành
`token`; R11/R13 ngắt sớm). Không chặn, nhưng nên bù: nhánh `replace` hiện **không có cổng nào**,
mà nó là thứ quyết định có được stream chữ ra hay không.

## F-7 — **đã chạy**, và nó làm đúng việc của nó

```
after   api_error=0/30 | 8 case cu tool 22/24 | 3/3: 01,02,03,04,05,06,09 | case10 3/3 | case11 3/3
stream  api_error=0/30 | 8 case cu tool 22/24 | 3/3: 01,02,   04,05,06,09 | case10 3/3 | case11 3/3
```

Tổng bằng nhau (22/24) nên **cổng viết theo micro-average sẽ báo xanh**. Nhưng soi **từng case** —
đúng nguyên tắc F-4 vừa sửa vào §8 — thì **case 03 tụt 3/3 → 2/3**, còn case 07 nảy lên 1/3 → 2/3
che mất phần chênh. Đây chính là lý do cổng phải so từng case chứ không so số gộp.

## F-10 — **Major.** Luật "kể lý do chọn tool" (bước 22b) làm hỏng case 03

Case 03 = *"xoá amount_paid thì vỡ gì?"*, `must_call: assess_change`. Lượt hỏng gọi
`['search_tables', 'search_column_description']` rồi dừng, **không tới `assess_change`**.

Tôi A/B **hai chiều**, N=5 mỗi bên, bằng cách bóc đúng một dòng luật khỏi prompt của `agent_node`
(không sửa `src/`, chỉ bọc `get_llm`):

| Chiều chạy | CÓ luật kể lý do | KHÔNG có luật |
| --- | --- | --- |
| mới trước | **1/5** | 5/5 |
| cũ trước | **3/5** | 5/5 |
| **gộp cả eval** | **6/13** | **16/16** |

**Hai chiều đồng ý** — khác hẳn case 07 (ở đó hai chiều ngược nhau nên tôi đã kết luận "không đủ
bằng chứng"). Cơ chế cũng nhìn thấy được: có luật thì agent mở màn bằng `search_tables` rồi sa vào
`search_column_description`; bỏ luật thì nó đi thẳng `search_column_description → assess_change`.

Plan đã lường trước rủi ro này (C-6: *"luật này nằm trong prompt của agent nên có thể làm lệch lựa
chọn tool — đó là lý do lượt eval sau M-8 là cổng bắt buộc"*). Cổng đã làm đúng việc; giờ là lúc
trả giá.

**Ba đường, tôi khuyên đường 1:**

1. **Bỏ dòng luật 22b.** Mất gì: sự kiện `thought` sẽ hiếm khi có nội dung (đo trước đây: 3/6
   lượt). Không mất gì đáng kể về trải nghiệm: phần lãi chính của M-8 là **dòng tiến trình tất
   định** từ `stepLabel` — §2.7 đo được nó xuất hiện ở ~1.36s so với câu trả lời ~3.4s. Giao thức
   giữ nguyên sự kiện `thought`, chỉ là model không tự nguyện thì không có.
2. Giữ luật, chấp nhận case 03 ~60%. Trái tinh thần "không nới cổng cho vừa kết quả".
3. Giữ luật nhưng đưa narration ra khỏi lượt chọn tool (một lời gọi LLM riêng). Thêm độ trễ —
   đúng thứ M-8 sinh ra để giảm.

Sau khi quyết: chạy lại `chat-context-and-ux-stream.json` và so **từng case** với `after`.

## Việc tiếp theo

1. Người ra đề quyết F-10.
2. Bù các hàng test §5 còn thiếu, ưu tiên `chat_verify_mode="replace"`.
3. Chạy lại eval, so từng case.

---

# Code review — bản sửa F-10

Ngày 2026-08-30.

## Kết luận

**Nửa đầu của phương án 1 làm xong và có kết quả rất rõ; nửa sau chưa làm.** Bỏ luật narration đã
đưa case 03 về **3/3** — chẩn đoán F-10 được xác nhận bằng chính lượt eval. Nhưng **phần thay thế
cho narration thì chưa có**: `stepLabel` không đổi một dòng nào và UI vẫn chỉ hiện dòng cuối. Nếu
dừng ở đây thì người dùng **mất narration mà không được gì bù lại**.

```
$ .venv/bin/pytest -q      626 passed, 60 skipped
$ npm test                 6 files, 19 tests
```

## Đã xong

**Luật narration đã xoá** khỏi `agent_node`, và **có cổng chặn thêm lại** —
`test_chat_graph.py:921`:

```python
assert "briefly state in Vietnamese why that tool is needed" not in agent_prompt
```

**Eval chạy lại (04:43), so từng case với `after` — đúng cách F-4 đòi:**

```
case | after | stream
  03 |  3/3  |  3/3   <- ve lai, dung nhu chan doan F-10
  07 |  1/3  |  2/3   <- len
  10 |  3/3  |  3/3
  11 |  3/3  |  3/3
  con lai: 3/3 o ca hai
```

`api_error` 0/30, model đúng, **không case nào tụt**. Đây là lần đầu trong cả task mà mọi case cũ
đều 3/3 trừ case 07 vốn đã bất ổn từ trước. Bằng chứng cho F-10 khép lại: A/B nói luật đó hại,
và gỡ nó ra thì case 03 hồi đúng như dự đoán.

## F-11 — **Major.** Phần thay thế narration chưa được cài

Plan §2.7 mục D, bảng C-6, bước 25 và 26 (sửa cùng lượt anh duyệt "sửa plan đi") yêu cầu dòng tiến
trình nói **cả việc làm lẫn kết quả**, và UI hiện **cả vệt** chứ không chỉ dòng cuối. Thực tế:

**`chatSteps.ts` không đổi một ký tự** — vẫn chỉ dùng `tool` + `args`, vứt `summary`:

```ts
if (step.tool === "breaking_changes") return "Đang kiểm cảnh báo đổi tên/xoá bảng…";
```

trong khi `ChatStep` mang sẵn kết quả (`summary='0 confirmed, 0 pending'` cho bước đó). Theo bảng
C-6 phải là:

```
Kiểm cảnh báo đổi tên/xoá cho insurance_risk_alerts → không có cảnh báo nào.
Truy ngược upstream của insurance_risk_alerts.high_risk_claim → 3 quan hệ đã xác nhận.
```

**`FloatingChatbot.tsx:381` vẫn chỉ render dòng cuối:**

```tsx
<span>{thought || progress.at(-1) || 'AI đang phân tích DAG đồ thị & bảng dữ liệu...'}</span>
```

`progress` đã gom đủ cả danh sách ở `:78` rồi bỏ phí. Mà **cả vệt mới đọc ra mạch suy luận** —
*không có cảnh báo → nên đi tiếp vào lineage* — chứ một dòng rời thì không.

**`chatSteps.test.ts` vẫn 2 khẳng định cũ**, chưa có ca nào kiểm phần kết quả (`0 confirmed,
0 pending` → `không có cảnh báo nào`; `3 confirmed` → `3 quan hệ đã xác nhận`; có pending → kèm
`1 chưa duyệt`) như §5 đã ghi.

**Vì sao đáng làm nốt, không phải cầu toàn:** cả M-8 sinh ra để lấp 2 giây im lặng trước khi câu
trả lời hiện ra (§2.7: sự kiện đầu ở ~1.36s, câu trả lời ~3.4s). Bỏ narration là đúng — nó hại
chất lượng chọn tool. Nhưng thứ được hứa thay vào chỗ đó vẫn chưa có, nên hiện người dùng chỉ thấy
một dòng "Đang tra upstream của…" rồi thôi.

## F-8 (còn lại) — **Minor.** Ba hàng test M-8 vẫn thiếu

`chat_verify_mode="replace"` → không phát `token`; `ToolMessage` của node `tools` không lọt thành
`token`; R11/R13 ngắt sớm → không turn/clarification/trace, session row rỗng. Nhánh `replace` vẫn
là nhánh **không có cổng nào** dù nó quyết định có được stream chữ ra hay không.

## Việc tiếp theo

1. F-11: `stepLabel` dùng `summary` theo bảng C-6, UI render cả danh sách, thêm test kết quả.
2. F-8 còn lại: ít nhất test `chat_verify_mode="replace"`.
3. Không cần chạy lại eval cho F-11 — nó thuần frontend, không đụng prompt hay tool.

---

## Provenance — phần Claude tự thi công theo yêu cầu trực tiếp

Ngày 2026-08-30.

**Nguồn thay đổi:** Claude Code tự thi công theo yêu cầu trực tiếp của người ra đề.
Mục này được ghi tách riêng để không lẫn với phần do Codex thi công hoặc các finding
Claude chỉ review/đề xuất.

- Phạm vi Claude tự thi công: các thay đổi được người ra đề chỉ định trực tiếp trong
  lượt này.
- Trạng thái review/verification của các thay đổi đó phải được ghi ở mục review tiếp
  theo; dòng provenance này **không** tự xác nhận rằng test hoặc eval đã xanh.

---

## Audit của Codex — phần Claude tự thi công M-9

Ngày 2026-08-30. Reviewer: Codex. Phạm vi: M-9 trong `query_nodes.py`,
`resolve.py`, `chat_service.py`, `test_chat_graph.py` và report eval M-9.

### Kết quả hành vi

M-9 đúng cơ chế C-7: `needs_selection` được tự gỡ ngay sau `capability.run()` và
trước `_summary`, nên `ToolMessage`/`ChatStep` nhận success result thay vì error.
Helper `mentions_identifier` giữ biên identifier và không phân biệt hoa thường.
Test mới phủ đúng một candidate, 0 candidate, 2 candidate, và substring không trọn.

Các lệnh đã chạy:

```text
.venv/bin/pytest -q tests/test_agents/test_chat_graph.py tests/test_agents/test_chat_resolve.py tests/test_services/test_chat_service.py
97 passed in 0.49s

make lint
All checks passed!

.venv/bin/ruff check eval
All checks passed!

mypy allowlist diff
(rỗng; chỉ còn diagnostic nền routes.py như expected)
```

`eval/results/chat-context-and-ux-m9.json` đạt `micro_average=1.0`; case 07 đạt
3/3 (`search_tables → traverse`) và case 03 vẫn 3/3.

### Finding

**F-12 — Minor — scope plan chưa nêu M-9 cho `src/agents/chat/resolve.py`.**
Claude đặt helper chung `mentions_identifier`/`question_with_choice` ở file này,
là lựa chọn kỹ thuật hợp lý để tránh copy regex Python. Nhưng §9 của plan hiện
chỉ cho `resolve.py` ở M-2. Cập nhật hàng §9 để ghi rõ M-9 được thêm helper biên
identifier dùng chung C-1/C-7; không cần đổi mã.

Ngoài F-12, phần Claude tự thi công M-9 đạt contract và không có finding blocker
hay major.

---

# Code review — M-9 + F-11

Ngày 2026-08-30 · phạm vi: `git diff` + `eval/results/chat-context-and-ux-m9.json`.

## Kết luận

**Chấp nhận.** Lần đầu tiên trong cả task **cả 10 case đều 3/3**. Case 07 — case duy nhất chưa
bao giờ xanh suốt từ đầu — nay xanh cả ba lượt, và đúng bằng cơ chế đã chẩn đoán. Không có finding
chặn; còn ba việc nhỏ ghi ở cuối.

```
$ .venv/bin/pytest -q      630 passed, 60 skipped   (+4)
$ make lint                All checks passed!
$ cong mypy §6             DAT
$ npm test / typecheck     6 files, 20 tests / sach
```

## M-9 — đạt, và đặt đúng chỗ R20 đòi

```
:570   result = capability.run(params, state["database_id"])
:571   if result is not None and result.error == "needs_selection":   <- xen dung khe
:583   summary = _summary(result)
```

Đúng yêu cầu R20: tự gỡ **trước** khi đóng gói payload, nên `ToolMessage` mang kết quả thành công
và `ChatStep` không có `error`.

**Eval, so từng case với `stream` (đúng cách F-4 đòi):**

```
case | stream | m9
  07 |   2/3  | 3/3   <- ca ba luot deu ['search_tables','traverse']
  con lai: 3/3 -> 3/3, khong case nao tut
api_error 0/30, model dung, ts 05:24
```

**Test gác thật.** Tôi tắt `_mentions_identifier` (trả `False`) rồi chạy lại:

```
FAILED test_search_selection_uses_one_candidate_named_in_question
```

Test này khẳng định đúng thứ cần khẳng định: payload mà **agent nhận được** là
`{"tables": ["underperforming_doctors"]}`, `clarification is None`, đủ **2** steps, và
`steps[0]["error"] is None` — tức chứng minh cả hành vi lẫn **vị trí** của bản sửa.

Ca âm được tham số hoá ba kiểu, phủ đúng ba rủi ro: hai ứng viên cùng xuất hiện → vẫn hỏi lại;
không ứng viên nào → vẫn hỏi lại; và `doctor_workloads` **không** được khớp `doctor_workload`
(biên định danh).

Hai test clarification cũ **không bị sửa dòng nào** — đúng cổng §8 của M-9.

## F-11 — đóng

`stepLabel` nay đọc `summary` qua `resultLabel`, đúng bảng C-6: `0 confirmed, 0 pending` →
`không có cảnh báo nào` (với `breaking_changes`) hoặc `không thấy quan hệ nào`; có pending thì
thêm `N chưa duyệt`. Và `FloatingChatbot.tsx:383` render **cả danh sách** thay vì `progress.at(-1)`.
Người dùng giờ đọc được cả vệt:

```
Kiểm cảnh báo đổi tên/xoá cho insurance_risk_alerts → không có cảnh báo nào.
Truy upstream của insurance_risk_alerts.high_risk_claim → 3 quan hệ đã xác nhận.
```

## Ba việc nhỏ còn lại — không chặn

**1. Helper đặt khác chỗ plan chốt.** Plan (C-7, §9) chốt để helper biên identifier ở
`src/agents/chat/resolve.py`. Thực tế cả `_mentions_identifier` lẫn `_question_with_choice` nằm ở
`src/agents/nodes/query_nodes.py`, và `chat_service.py:26` import **hàm private** từ đó:

```python
from src.agents.nodes.query_nodes import _question_with_choice, compose_node, verify_node
```

Không vòng import (chiều `chat_service → query_nodes` vốn đã có) và **chỉ một** regex trong toàn
`src/`, nên mục tiêu đạt. Nhưng import tên `_private` xuyên module là mùi, và nó ngược layering:
`_question_with_choice` là việc của tầng service, giờ sống trong module node. **Đề xuất:** chuyển
cả hai sang `resolve.py` như plan, hoặc bỏ dấu `_` để nó thành API công khai có chủ đích. Việc
nhỏ, nhưng nên chốt kẻo lần sau ai đó lại thêm regex thứ hai cho "gọn".

**2. Thiếu test đồng bộ hai bản cài đặt (R21).** `grep -rn "_mentions_identifier" tests/` không ra
gì. Bộ ca chung ở C-7 (khớp trong câu; `doctor` không khớp `doctor_workload`; trong backtick; khác
hoa thường) hiện chỉ được kiểm ở phía TS (`linkifyEntities.test.ts`) và gián tiếp qua test M-9.
Một test Python gọi thẳng helper trên đúng bộ ca đó là rẻ và chặn được trôi lệch giữa hai bản.

**3. Ba hàng test M-8 vẫn thiếu** (nhắc lần thứ ba, vẫn không chặn): `chat_verify_mode="replace"`
→ không phát `token`; `ToolMessage` không lọt thành `token`; R11/R13 ngắt sớm. Nhánh `replace`
vẫn **không có cổng nào** dù nó quyết định có được stream chữ ra hay không.

## Trạng thái

M-0 → M-9 **xong**. Mười case eval 3/3, mọi cổng xanh. Ba việc trên đều là dọn dẹp, người ra đề
quyết làm hay để lại.

---

# Ba việc dọn dẹp — **Claude tự thi công** theo yêu cầu trực tiếp

Ngày 2026-08-30 · người ra đề: *"làm hết đi"*. Ghi rõ ở đây vì bình thường Claude không viết mã
sản phẩm (CLAUDE.md); đây là ngoại lệ được nêu tên, và cần để lại dấu vết ai làm gì.

```
$ .venv/bin/pytest -q      642 passed, 60 skipped   (truoc: 630)
$ make lint                All checks passed!
$ .venv/bin/ruff check eval  All checks passed!
$ cong mypy §6             DAT
$ npm test / typecheck     6 files, 20 tests / sach
```

## 1. Helper về đúng nhà (`resolve.py`), hết import hàm private

`mentions_identifier` và `question_with_choice` chuyển từ `query_nodes.py` sang
`src/agents/chat/resolve.py`, **bỏ dấu `_`** vì chúng là API dùng chung thật sự. Cả hai nay dựng
trên **một** hằng số biên:

```python
_IDENTIFIER_BOUNDARY = "A-Za-z0-9_."
def _identifier_pattern(name): return rf"(?<![{_IDENTIFIER_BOUNDARY}]){re.escape(name)}(?![{_IDENTIFIER_BOUNDARY}])"
```

`chat_service.py` và `query_nodes.py` cùng import từ `resolve` — hết cảnh tầng service import hàm
private của module node. `import re` thừa trong `query_nodes.py` đã gỡ. Khớp đúng chỗ plan chốt ở
C-7/§9.

Một khác biệt nhỏ có chủ ý: `mentions_identifier(text, "")` nay trả `False`. Bản cũ để rỗng lọt
vào regex và khớp bừa. Ứng viên không bao giờ rỗng trong thực tế, nên không đổi hành vi đo được.

## 2. Test đồng bộ hai bản cài đặt (R21)

`tests/test_agents/test_chat_resolve.py`: 8 ca tham số hoá, **chép đúng bộ ca của
`linkifyEntities.test.ts`** — `underperforming_doctors` khớp trong câu; `doctor_workload` không
khớp khi câu chỉ có `doctor`; `doctor_workloads` không khớp `doctor_workload`; tên trong backtick;
khác hoa thường; `revenue_alerts_finalized` không khớp `revenue_alerts_final`; tên có dấu chấm.
Cộng một test khẳng định `question_with_choice` dùng **cùng** luật biên.

## 3. Ba test M-8 còn thiếu — và một cái bẫy tôi suýt tự sập

`tests/test_api/test_chat_routes.py`: `verify_mode="replace"` → không token; ToolMessage không
lọt thành token; ngắt sớm → không turn/clarification/trace.

**Bẫy:** viết xong bằng `set_llms` thì cả ba xanh — nhưng `FakeLLM` **không phải model LangChain**
nên không sinh callback nào, tức **không có token nào được phát** và hai test về token vô nghĩa y
hệt lỗi tôi từng bắt ở F-1. Tôi phát hiện vì cố tình đặt `assert tokens, "phai co token that de
phep kiem nay co nghia"` và nó đỏ.

Sửa: thêm `set_streaming_compose()` dùng `GenericFakeChatModel` — model giả **biết stream thật** —
cho node compose. Nay compose nhả 5 chunk thật.

**Kiểm hai test đó có gác không, không tin vào màu xanh:**

```
tat cong verify_mode (ep chat_service luon thay "warn")
  -> FAILED test_stream_emits_no_token_when_verify_mode_replaces_the_answer

premise cua test chong ro ri (do that):
  chunk theo node: [('tools', '{"ok": true, "table": "raw.o'), ('agent','DONE'),
                    ('compose','cau'), ('compose',' '), ('compose','tra'), ...]
```

Node `tools` **thật sự** nhả JSON thô ra kênh `messages`; bỏ bộ lọc `langgraph_node == "compose"`
là nó chảy thẳng vào bong bóng chat và test sẽ đỏ.

## Không chạy lại eval

Ba việc trên không đụng prompt, không đụng lựa chọn tool, không đụng hợp đồng tool. Helper chỉ đổi
chỗ ở với cùng một biểu thức. `chat-context-and-ux-m9.json` (10/10 case 3/3) vẫn là số đo đúng cho
mã hiện tại.
