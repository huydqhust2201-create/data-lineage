# Danh mục câu hỏi cho Chat Lineage

Liệt kê **các dạng câu hỏi (pattern)** người dùng có thể đặt — không liệt kê theo bảng.
Mỗi pattern gồm ba phần:

- **Luồng tool** — thiết kế: gọi tool nào, thứ tự nào, tham số gì. Đây là luồng
  **nên có**, không phải luồng agent đang chạy.
- **Đáp án phải có** — hợp đồng nội dung. Thiếu thứ này thì câu trả lời sai dù dài.
- **Thiếu năng lực** — chỗ tool hiện tại không đỡ được, kèm đề xuất sửa/thêm tool.

## Cách đọc

**Nguồn ví dụ** — câu 🔵 là **người dùng đã hỏi thật**, lấy từ `logs/chat-traces/*.jsonl`
(565 lượt, 14 câu khác nhau, 27–28/08/2026). Câu không đánh dấu là soạn để phủ pattern,
**chưa từng chạy**.

**Trạng thái** — chỉ ghi khi có đo hoặc quan sát thật:

| | |
| --- | --- |
| ✅ | Đã đo, đạt |
| ⚠️ | Chạy được nhưng trả lời thừa / lệch trọng tâm |
| ❌ | Đã quan sát thấy trả lời sai hoặc thiếu đúng thứ được hỏi |
| ⛔ | Chưa hỗ trợ — thiếu dữ liệu hoặc thiếu tool |
| — | **Chưa đo.** Không suy đoán. |

Số ✅/❌ lấy từ `eval/results/chat-analysis-tools-after.json` (N=10/case,
`google/gemini-3.5-flash-lite`, 2026-08-28) hoặc từ trace thật, có ghi nguồn.

## Bộ câu hỏi test tay — chat context, streaming và M-9

Dùng các câu sau để smoke-test chatbot trên `database_id=1`:

| Câu hỏi | Kỳ vọng chính |
| --- | --- |
| `làm thế nào để 1 doctor được đánh dấu là underperforming_doctors?` | Không hỏi chọn bảng khi agent tìm `doctor`; tiếp tục `search_tables → traverse`, trả `appointment_count` và ngưỡng `5`. |
| `underperforming_doctors lấy dữ liệu từ đâu?` | Tra lineage upstream của bảng. |
| `doctor_workload và underperforming_doctors liên quan thế nào?` | Không tự chọn khi câu hỏi nêu từ hai ứng viên; clarification vẫn là hành vi đúng. |
| `doctor_workloads là gì?` | Không coi `doctor_workloads` là khớp trọn với `doctor_workload`. |
| `xoá amount_paid thì vỡ gì?` | Gọi `assess_change`. |
| `cột high_risk_claim của insurance_risk_alerts đang sai, tại sao?` | Kiểm breaking changes rồi tra upstream; nêu giả thuyết có neo fact. |
| `số liệu cột abnormal_lab_count trong patient_risk_score bị lệch, nguyên nhân có thể là gì?` | Kiểm breaking changes rồi tra upstream; nêu giả thuyết có neo fact. |
| `revenue_alerts_final lấy dữ liệu từ đâu?` | Có progress step trước khi câu trả lời hoàn tất. |

Với các câu có tool, UI streaming phải hiển thị đủ vệt tiến trình; mỗi dòng có hành động và kết quả.

## Đồ thị nền

Sample `hospital`, `database_id=1`: **36 bảng, 83 cạnh**.
15 bảng nguồn, 12 trung gian, 9 mart.

- `transform_type`: `direct` 69, `aggregation` 11, `unknown` 3 — **`join` = 0**.
- `source_type`: `parser` 50, `llm` 33.
- **`pending` = 0** → mọi pattern về HITL không có dữ liệu để đo ở đây.
- `department_revenue` **đã bị drop** (kịch bản `breaking_change_demo`, ingest 2 lượt).

## Bộ tool hiện có (9)

| Tool | Tham số | Dùng cho pattern |
| --- | --- | --- |
| `traverse` | `table, direction, column, depth` | C1 C2 C3 D1 D2 D3 |
| `assess_change` | `table, column, change_kind` (**8** giá trị) | E1 E2 E3 E4 E6 E7 |
| `search_tables` | `query, limit` | A1 H2 H3 H5 |
| `list_relationships` | `status, limit` | A4 |
| ~~`get_asset`~~ | — | **Đã rút khỏi REGISTRY (T-0d).** `asset_tools.py` và `AssetProfile` còn nguyên, chỉ không đăng ký. Các pattern trước dùng nó nay đi đường khác — xem B1, B2, F1, I2 |
| `search_by_description` | `query, limit` | A2 |
| `search_column_description` | `query, limit` | A3 B2 |
| `preview_ddl_impact` | `sql, dialect` | E5 |
| `breaking_changes` | `tables` | F1 F2 |
| `analyze_query` | `sql, dialect` | G1 G2 G3 |
| ~~`search_sql_content`~~ | — | **Đã rút khỏi REGISTRY.** Tool của main (RAG trên văn bản SQL). Chỉ mục SQL của `database_id=1` **rỗng** (`count_searchable_sql_documents = 0`) vì đồ thị được ingest trước khi main thêm bước embed SQL. Khi gọi trực tiếp, tool nay trả `error="index_empty"`; vẫn chưa đăng ký lại cho chat cho tới khi index có dữ liệu. Xem pattern **C6** và §R2c |

**Ràng buộc phải nhớ khi đề xuất tool mới:** đo 2026-08-28 cho thấy ở **10 tool**,
pattern C2 rơi từ 1.00 xuống **0.20**; ba cấu hình **9 tool** khác nhau (bỏ
`analyze_query`, bỏ `get_asset`, bỏ `list_relationships`) đều phục hồi **1.00**.
Thêm tool thứ 11 là **có giá**, phải đo lại toàn bộ. Vì vậy các đề xuất dưới đây ưu
tiên **thêm trường / thêm tham số vào tool sẵn có** hơn là tạo tool mới.

---

# A. Định hướng — chưa biết hệ thống có gì

### A1. Có những bảng nào?
> Hệ thống đang có những bảng nào? / Liệt kê các bảng liên quan tới invoice.

**Luồng:** `search_tables(query=<fragment hoặc rỗng>, limit)`
**Đáp án phải có:** tên bảng thật; nói rõ khi bị cắt bớt (`search_truncated`).
**Thiếu năng lực:** không. Trạng thái: —

### A2. Bảng nào chứa dữ liệu về <chủ đề>?
> Bảng nào chứa dữ liệu doanh thu theo khoa?

**Luồng:** `search_by_description(query=<mô tả>)`
**Đáp án phải có:** tên bảng + mô tả đã lưu; không bịa bảng ngoài kết quả.
**Thiếu năng lực:** không. Trạng thái: —

### A3. Cột nào mang ý nghĩa <…>?
> Cột nào cho biết bệnh nhân có bảo hiểm hay không?

**Luồng:** `search_column_description(query=<mô tả>)`
**Đáp án phải có:** cặp `table.column` + mô tả.
**Thiếu năng lực:** ⛔ **Tool này hiện là tool chết** — kết quả không tới được agent lẫn
compose (§R2). Pattern A3 vì thế **chưa từng trả lời được**, dù tool chạy và tìm đúng cột.
Trạng thái: ❌

### A4. Hệ thống biết những quan hệ gì / có gì chờ duyệt?
> Có quan hệ nào đang chờ duyệt không? / Lần ingest vừa rồi tìm được gì?

**Luồng:** `list_relationships(status='pending'|'confirmed'|'all')`
**Đáp án phải có:** số lượng + phân biệt confirmed / pending.
**Thiếu năng lực:** không. Trạng thái: — (`pending=0` nên nhánh "có pending" chưa đo được)

---

# B. Định nghĩa — cái này là gì

### B1. Bảng X là gì?
> 🔵 `underperforming_doctors là gì`

**Luồng:** `traverse(table=X, direction='upstream', depth=1)` — mô tả bảng tới compose qua
`table_descriptions` **bất kể** gọi tool nào, nên không cần tool riêng. **Dừng ở đây**, không
đi sâu thêm.
**Đáp án phải có:** mô tả nghiệp vụ đã lưu + cột sinh ra. **Không** kèm cây lineage.
**Thiếu năng lực:** không thiếu tool — thiếu **rule dừng**.

Trạng thái: ✅ Sau T-0d, đo thật: `traverse` một lượt, **209 ký tự**, trả đúng mô tả nghiệp
vụ rồi dừng.

*(Nền trước T-2: **3.402 ký tự** — gọi `get_asset` rồi gọi thêm `traverse`, trả mô tả một câu
rồi đổ tiếp `### Confirmed Upstream Sources` kèm công thức từng cột, cho một câu hỏi "là gì".)*

**Đề xuất:** rule trong prompt compose — câu hỏi định nghĩa thì trả định nghĩa, gợi ý
người dùng hỏi tiếp về nguồn gốc, **không** tự đổ nguồn gốc ra.

### B2. Cột X nghĩa là gì?
> `amount_paid` là gì?

**Luồng:** `search_column_description(query=<tên cột>)` — sau T-0c nó khớp **tên cột** trước
rồi mới tìm ngữ nghĩa, và trả kèm mô tả đã lưu khi có.
**Đáp án phải có:** mô tả cột; nếu chưa có mô tả thì nói thẳng là chưa có.
**Thiếu năng lực:** không. Trạng thái: —

---

# C. Nguồn gốc — dữ liệu này ở đâu ra

### C1. Bảng X lấy dữ liệu từ đâu?
> 🔵 `revenue_alerts_final lấy dữ liệu từ đâu?` · 🔵 `underperforming_doctors được lấy từ đâu`

**Luồng:** `traverse(table=X, direction='upstream', depth=2)`
**Đáp án phải có:** các bảng nguồn **trực tiếp**; gộp theo cặp bảng, không liệt kê từng cột.
**Thiếu năng lực:** `depth` mặc định đang là `None` = **vô hạn**.

Trạng thái: ✅ pass_rate **1.00** — nhưng median **2.011** ký tự (n=60), max 3.546.

**Đề xuất:** `traverse.depth` mặc định **2**; muốn sâu hơn thì model tự nâng (xem C3).

### C2. Cột X tính thế nào?
> 🔵 `projected_revenue tính thế nào?`

**Luồng:** `traverse(table=X, column=<cột>, direction='upstream', depth=2)`
**Đáp án phải có:** **biểu thức** (`transform_expression`), không chỉ tên bảng nguồn.
**Thiếu năng lực:** không thiếu tool. Gốc là **R2b** — `projected_revenue` không có mô tả
cột nên tìm ngữ nghĩa trượt, và tool không báo trượt.

Trạng thái: ✅ **1.00** sau T-0c. *(Lịch sử: 0.20 ở 10 tool, 1.00 ở 9 tool, 7/10 lần gọi
`search_column_description` thay vì `traverse` — từng bị quy nhầm cho bão hoà tool §R1.)*

**Đã sửa bằng T-0c:** khớp **tên cột** trước, ngữ nghĩa sau, kèm `match_kind`. Không thêm tool.

### C3. Truy ngược tới tận nguồn thô
> `revenue_alerts_final` cuối cùng bắt nguồn từ bảng raw nào?

**Luồng:** `traverse(table=X, direction='upstream', depth=<lớn hoặc None>)`
**Đáp án phải có:** **chuỗi rút gọn** `raw_x → stg_x → … → X`, không phải danh sách cạnh.
**Thiếu năng lực:** không có cách diễn đạt "tóm tắt chuỗi" — facts là danh sách cạnh phẳng.

Trạng thái: ❌ **lê thê nghiêm trọng.** Một câu hỏi C1 tự đi tới hop 3 và trả
**5.319 ký tự**: 16 cạnh, mỗi cột một gạch đầu dòng, 5 dòng riêng cho
`raw_appointments → stg_appointments`, `citation was not verified` **16 lần**,
`(SQLGlot's normalised representation)` 11 lần.

**Đề xuất:** gộp cạnh theo `(source, target, hops)` ở tầng facts + ngân sách gạch đầu dòng.

### C4. Điều kiện để một dòng lọt vào bảng X là gì? ⭐
> 🔵 `làm thế nào để 1 doctor được đánh dấu là underperforming_doctors`
> 🔵 `underperforming_doctors được lấy như nào`

**Luồng thiết kế:**

```
traverse(table='underperforming_doctors', direction='upstream', depth=1)
    -> canh mang filter_condition = "appointment_count < 5"    <-- TRUONG CHUA TON TAI
```

**Đáp án phải có:** đúng vị từ `appointment_count < 5`, và nhánh điều kiện — `flag_low_volume_doctors`
bật thì lấy từ `doctor_workload` **kèm** điều kiện đó, tắt thì từ `hr_review_flagged_staff`
**không** lọc. Đáp án gọn trong ~2 câu.

**Thiếu năng lực:** `LineageEvidence` chưa có `filter_condition`. Điều kiện chỉ tồn tại
trong `evidence.raw_sql` (nguyên văn cả file), không được trích ra trường riêng nào.

**Tính toán được chưa — được.** Hai tuyến trích **bù nhau**, đo trên 12 bảng có điều kiện lọc:

| Nhóm | Số bảng | Ai trích |
| --- | --- | --- |
| Có Jinja `{% if %}` | **8** | LLM extraction (parser fail, LLM vốn đã đọc `raw_sql`) |
| Không Jinja | **3** | SQLGlot trích `WHERE`/`HAVING` |
| Không Jinja, vẫn llm | 1 | LLM |

Gộp lại **có thể** phủ 12 bảng, nhưng gánh nặng chính ở LLM: phía parser chỉ
`readmission_flag` có `WHERE` thật; `insurance_risk_alerts` và `patient_risk_score` dùng
`CASE` — hình thái khác, không phải mệnh đề lọc. *(Con số "parser chỉ phủ 1/12" ở các bản
trước là parser-only trên cả 12 bảng — nhưng 8 bảng trong đó **không đi qua parser**.)*

**Đề xuất — trích lúc ingest, gắn vào cạnh:**
- `LineageEvidence` thêm `filter_condition: str | None`, nguyên văn, không diễn giải.
- Gắn vào **cạnh** chứ không vào bảng: điều kiện khác nhau theo nhánh, mà nhánh quyết định
  bảng nguồn.
- `traverse` trả về luôn → **không cần** đổi tool, không cần định tuyến sang `get_asset`.
- **Cần xoá đồ thị rồi ingest lại toàn bộ** — `graph_service.add_edge` chỉ ghi đè evidence
  khi confidence cao hơn, nên ingest chồng lên sẽ giữ nguyên evidence cũ.

*(Phương án cũ — `get_asset(include_definition=true)` trả `definitions[].sql` cho model đọc
lúc chat — **đã bỏ**: nó phụ thuộc vào việc agent chịu đổi tool, mà đo được là agent không chịu.)*

### C5. Bảng này nối với bảng kia qua điều kiện nào? ⭐
> `doctor_workload` nối với `stg_doctors` qua đâu?
> `doctor_id` trong `doctor_workload` khớp với cột nào bên `stg_appointments`?

**Luồng thiết kế:** giống hệt C4 — `traverse(...)`, cạnh mang `join_condition`.

**Đáp án phải có:** cặp cột được nối (`doctors.doctor_id = appts.doctor_id`) và hai bảng
tham gia. **Cấm gọi đó là khoá chính / khoá ngoại** — xem dưới.

**Tính toán được chưa — được, cùng cơ chế với C4.** SQLGlot trích mệnh đề `ON` thành công
**5/5** bảng có JOIN, không ca nào chết vì Jinja:

```sql
LEFT JOIN appts ON doctors.doctor_id = appts.doctor_id
```

Một cơ chế (trích lúc ingest, gắn vào cạnh) phủ cả C4 lẫn C5. `LineageEvidence` thêm
`join_condition: str | None` bên cạnh `filter_condition`.

**Vì sao không gọi là PK/FK.** `ON a.x = b.y` chứng minh hai cột **được nối trong query
này**, không chứng minh cột nào là khoá chính, khoá ngoại, duy nhất, hay có ràng buộc tham
chiếu. Hai cột không constraint vẫn join được; một FK thật vẫn có thể chưa từng xuất hiện
trong SQL đã ingest.

Và không có nguồn nào để lấy PK/FK thật: `grep -rniE "primary key|foreign key|references "
samples/` → **0 constraint** trong toàn bộ sample (kết quả duy nhất là một chuỗi *mô tả*
trong `jaffle-shop/models/marts/orders.yml`). Muốn trả lời được "khoá chính của
`stg_patients` là gì" thì phải thêm DDL có constraint vào dữ liệu mẫu trước.

**Thiếu năng lực:** `LineageEvidence.join_condition` chưa tồn tại. Trạng thái: ⛔ chưa hỗ
trợ, sẽ có cùng lúc với C4.

### C6. File nào chứa đoạn logic này? ⛔ *(mới ghi nhận sau khi merge main)*
> Chỗ nào trong kho có điều kiện lọc theo số lịch hẹn?
> Model nào dùng macro `dbt_utils.star`?

**Ba câu hỏi dễ lẫn, khác nhau ở hai chỗ:**

| | Biết bảng nào chưa? | Tra trên cái gì |
| --- | --- | --- |
| **C4** | **Có** — đã biết bảng | `definition_sql` của chính bảng đó |
| **A2** | Chưa | **mô tả** bảng do LLM sinh |
| **C6** | Chưa | **văn bản SQL gốc** |

**Luồng thiết kế:** `search_sql_content(query=<mô tả đoạn logic>)`.

**Trạng thái: ⛔ chưa hỗ trợ trong chat.** Tool có sẵn từ main
(`src/agents/tools/sql_document_tools.py`) nhưng **đã rút khỏi REGISTRY** vì chỉ mục SQL của
`database_id=1` rỗng. Nếu gọi trực tiếp, nó trả `error="index_empty"` thay vì giả vờ đã tìm
nhưng không có kết quả.

**Đường quay lại:** nạp chỉ mục SQL (nằm trong đường ingest của main), rồi đăng ký lại. Điều
kiện an toàn đã có: §R2c đảm bảo index rỗng được báo rõ bằng `index_empty`.

# D. Tiêu thụ — cái gì đang dùng dữ liệu này

### D1. Những bảng nào đọc từ X?
> Bảng nào đang dùng `stg_invoices`?

**Luồng:** `traverse(table=X, direction='downstream', depth=2)`
**Đáp án phải có:** bảng phụ thuộc trực tiếp, gộp theo cặp.
**Thiếu năng lực:** không (dùng chung `depth` mặc định với C1). Trạng thái: —

### D2. Cột này được dùng ở đâu phía sau?
> `amount_paid` chảy đi những đâu?

**Luồng:** `traverse(table=X, column=<cột>, direction='downstream', depth=2)`
**Đáp án phải có:** cặp `bảng.cột` đích + biểu thức biến đổi nếu có.
**Thiếu năng lực:** không. Trạng thái: —

### D3. Bảng không có ai đọc
> Có ai đọc `revenue_alerts_final` không?

**Luồng:** như D1; kết quả rỗng là **kết luận thật**, không phải thiếu dữ liệu.
**Đáp án phải có:** nói rõ **chỉ theo hướng đó**; cấm suy ra "bảng này không có quan hệ
nào"; nhắc rằng hướng ngược lại hỏi riêng được.
**Thiếu năng lực:** không — prompt đã có rule riêng. Trạng thái: — (chưa có case eval)

---

# E. Tác động thay đổi — sửa cái này thì vỡ gì

### E1. Xoá một cột
> 🔵 `xoá amount_paid thì vỡ gì?` · 🔵 `xoá total_revenue thì vỡ gì?`

**Luồng:** `assess_change(table=X, column=<cột>, change_kind='drop')`
**Đáp án phải có:** cạnh downstream bị ảnh hưởng + ghi chú rủi ro **theo từng cạnh**.
**Thiếu năng lực:** không thiếu tool — model chọn nhầm.

Trạng thái: ❌ pass_rate **0.00** — gọi `search_column_description` thay vì
`assess_change`. Đã thử 6 model, không model nào qua (`chat-eval-and-guard.md` §0o).
Xem §R2: tool bị chọn nhầm đó báo `count: 0` dù tìm được cột, nên model dừng lại thay vì
thử tiếp — giả thuyết chưa đo.

### E2. Xoá cả bảng
> Xoá bảng `doctor_workload` thì vỡ gì?

**Luồng:** `assess_change(table=X, change_kind='drop_table')` — **không** dùng `'drop'`,
câu chữ rủi ro khác. Trạng thái: —

### E3. Đổi tên bảng / cột
> Đổi tên `stg_invoices` thành `stg_invoices_v2` thì sao?

**Luồng:** `assess_change(..., change_kind='rename'|'rename_table')`. Trạng thái: —

### E4. Đổi kiểu dữ liệu
> Đổi `amount_paid` từ int sang decimal thì ảnh hưởng gì?

**Luồng:** `assess_change(..., change_kind='type')`. Trạng thái: —

### E6. Thêm một cột mới
> Thêm cột `discount_rate` vào `stg_invoices` thì ảnh hưởng gì?

**Luồng:** `assess_change(table=X, column=<cột>, change_kind='add_column')`
**Đáp án phải có:** rủi ro **nhẹ nhất** trong 8 loại — không phá dữ liệu hiện có; rủi ro chỉ
đến từ downstream dùng `SELECT *` và nơi kiểm lược đồ cứng (silent schema drift).
**Thiếu năng lực:** không. Trạng thái: — *(mới có từ khi merge main, chưa case eval nào)*

### E7. Đổi ràng buộc trên cột đã có
> Thêm `NOT NULL` cho `amount_paid` thì sao? / Đổi khoá chính của `stg_patients` thì vỡ gì?

**Luồng:** `assess_change(table=X, column=<cột>, change_kind='constraint')`
**Đáp án phải có:** khác `'type'` và `'value'` — **không** đổi giá trị dữ liệu, nhưng có thể
**chặn ghi** dữ liệu hiện có (`NOT NULL`) hoặc **mất ràng buộc tham chiếu** (đổi FK).
**Thiếu năng lực:** không. Trạng thái: — *(mới có từ khi merge main, chưa case eval nào)*

### E5. Duyệt trước cả script DDL
> 🔵 `Nếu deploy \`DROP TABLE revenue_alerts_staging;\` thì những bảng nào bị ảnh hưởng?`

**Luồng:** `preview_ddl_impact(sql=<script>, dialect)` → *(tuỳ chọn)* `traverse` để nói
thêm về bảng bị ảnh hưởng.
**Đáp án phải có:** trình bày là **thay đổi đề xuất, CHƯA xảy ra**; rủi ro theo **thứ tự
câu lệnh** (`risk_by_statement`); nêu rõ câu lệnh không hỗ trợ / bảng lạ / xung đột rename.
**Cấm** kết luận script an toàn khi phân tích chưa đủ.

Trạng thái: ✅ pass_rate **1.00**, median 1.096 ký tự.

---

# F. Sự cố — có cái gì đó đang hỏng

**Nguyên tắc:** có sự cố thì **ưu tiên tìm breaking change trước**, hết mới tìm nguyên
nhân khác. Đã cài trong `breaking_change_tools.prompt_rules`.

### F1. Bảng X bị lỗi, tại sao?
> 🔵 `revenue_alerts_staging bị lỗi, tại sao?` · Sao báo cáo doanh thu sáng nay trống trơn?

**Luồng thiết kế:**

```
1. breaking_changes(tables=[X])           ← LUÔN GỌI TRƯỚC
2a. có alert  → trả lời ngay: bảng bị drop/đổi tên + bảng thay thế
2b. không có  → traverse(X, 'upstream', depth=2)
                rồi mới nói tới nguyên nhân khác
```

**Đáp án phải có:** nêu bảng bị drop/đổi tên **trước** khi liệt kê phụ thuộc; trình bày
là **nguyên nhân khả dĩ**, không phải quan hệ nhân quả đã chứng minh.

Trạng thái: ✅ pass_rate **1.00** — nhưng median 1.002 ký tự với **max 15.167**. Đuôi dài
mới là vấn đề ở pattern này.

**Hai biến thể theo trạng thái đồ thị** — cùng câu hỏi, dữ liệu nền khác nhau. *(Chỉ
pattern này có biến thể; các pattern khác không.)*

| Biến thể | Đồ thị | Luồng | Đáp án phải có |
| --- | --- | --- | --- |
| **F1a — chưa ingest thay đổi** | Bảng nguồn **vẫn còn**; thay đổi xảy ra ngoài kho, chưa nạp | `breaking_changes` → rỗng → `traverse` | Nói rõ **chưa kiểm được** thay đổi ngoài kho; **cấm** kết luận "không có vấn đề gì" |
| **F1b — đã ingest thay đổi** | Ingest lượt 2 đã ghi drop/rename; bảng nguồn **biến mất** khỏi đồ thị, alert đã tạo | `breaking_changes` → có alert → trả lời ngay | Tên bảng bị drop + bảng thay thế + danh sách phụ thuộc |

F1b là kịch bản `samples/breaking_change_demo/` (`department_revenue` bị drop,
alert `#4 → [revenue_alerts_final, revenue_alerts_staging]`).

### F2. Không có alert nào
> `stg_invoices` có vấn đề gì không?

**Luồng:** `breaking_changes(tables=[X, …])`
**Đáp án phải có:** nêu **phạm vi đã kiểm** (`breaking_changes_checked_tables`); chỉ được
gọi bảng là "sạch" khi phạm vi đó phủ **cả** bảng gốc lẫn toàn bộ cạnh. Trạng thái: —

---

# G. SQL người dùng dán vào

### G1. Query này lấy dữ liệu từ đâu?
> 🔵 `Query này lấy dữ liệu từ đâu? SELECT d.department_name, SUM(i.amount_paid) … FROM stg_invoices i JOIN stg_doctors d …`

**Luồng:** `analyze_query(sql=<query>, dialect)` → *(tuỳ chọn)* `traverse` trên bảng nguồn
tìm được, nếu người dùng hỏi tiếp về gốc.
**Đáp án phải có:** bảng/cột nguồn **đã ghi nhận**; **cấm** nhắc lại SQL thô.

Trạng thái: ✅ pass_rate **1.00**, median 1.316 ký tự.

### G2. Query tham chiếu bảng lạ
> SELECT * FROM bang_khong_ton_tai

**Luồng:** `analyze_query(...)` → bảng không resolve được **không** vào vocabulary.
**Đáp án phải có:** nêu rõ bảng nào không có trong đồ thị. Trạng thái: —

### G3. Query không parse được
> Một đoạn SQL sai cú pháp

**Luồng:** `analyze_query(...)` → trả `note`/lỗi.
**Đáp án phải có:** báo không phân tích được; **cấm** bịa nguồn. Trạng thái: —

---

# H. Hội thoại và ca biên — nhóm dễ vỡ nhất

### H1. Câu hỏi nối tiếp dùng đại từ ⭐
> 🔵 `nó được lấy từ đâu` (sau khi vừa hỏi về `underperforming_doctors`)

**Luồng thiết kế:** **không gọi tool nào.** Không xác định được chủ thể → hỏi lại.

**Đáp án phải có:** câu hỏi lại — "bạn đang hỏi về bảng nào?". Nếu lượt trước trong cùng
database và cùng user có bảng thì đề xuất bảng đó để xác nhận.

Trạng thái: ❌ **Sai hẳn.** Trace thật, `database_id=1` (**36 bảng**): gọi
`list_relationships` với `args={}` → 0 kết quả → trả lời *"cơ sở dữ liệu đồ thị hiện đang
trống, bạn có thể chạy POST /ingest"*.

`graph_is_empty` tính ra **False**. Model **bịa** — prompt có rule cho
`graph_is_empty is true` và cho "root_table có + cả hai rỗng", nhưng **không có rule nào**
cho "không xác định được bảng và không có fact nào".

**Đề xuất:** thêm trường tính được `no_facts` vào facts + rule bắt buộc hỏi lại; cấm
`POST /ingest` trong ca này.

### H1a. Ngữ cảnh hội thoại thuộc database và user

Phiên chat không còn do client tạo bằng `session_id`. Backend lưu lịch sử và clarification
theo khóa **`(database_id, user_id)`**; cùng user hỏi tiếp trong cùng database thì thấy các
lượt trước, còn user hoặc database khác thì cô lập hoàn toàn.

**Hệ quả cho H1:** đại từ như “nó” chỉ có thể tham chiếu bảng của **chính user đó** trong
database đang mở. Không được dựa vào `session_id` trong request để nối ngữ cảnh.

### H2. Tên bảng nhập nhằng
> `revenue_alerts` lấy từ đâu? *(có cả `_staging` và `_final`)*

**Luồng:** resolve → `clarification` với `candidates`.
**Đáp án phải có:** liệt kê **đánh số** đủ mọi ứng viên, hỏi chọn, **không tự chọn**.
Trạng thái: —

### H3. Bảng không tồn tại
> `bang_khong_co` lấy từ đâu?

**Luồng:** resolve thất bại → `suggestions`.
**Đáp án phải có:** nói không tìm thấy + gợi ý tên gần đúng. Trạng thái: —

### H4. Hỏi ngoài phạm vi
> Tháng này khoa nào doanh thu cao nhất? / Bảng này có bao nhiêu dòng?

**Luồng:** **không gọi tool.**
**Đáp án phải có:** từ chối rõ ràng — hệ thống chỉ biết lineage, không đọc giá trị dữ
liệu, không đọc đầy đủ logic JOIN/WHERE. Trạng thái: —

### H5. Câu hỏi quá rộng
> Giải thích toàn bộ hệ thống cho tôi.

**Luồng:** `search_tables(limit)` → tóm tắt theo tầng → hỏi thu hẹp.
**Đáp án phải có:** tổng quan theo tầng (nguồn / trung gian / mart), **không** đổ 83 cạnh.
Trạng thái: —

---

# I. Tin cậy và bằng chứng

### I1. Cái này chắc chắn tới đâu?
> Quan hệ này là parser tìm ra hay LLM đoán?

**Luồng:** có sẵn trong facts của lần gọi trước, **không cần gọi thêm tool**.
**Đáp án phải có:** tách `confirmed` / `inferred_pending`; nói rõ pending là **giả thuyết
LLM chưa duyệt** kèm confidence. Trạng thái: — (`pending=0`, chưa đo được)

### I2. Căn cứ ở file nào?
> Chỗ nào trong code định nghĩa cái này?

**Luồng:** không cần tool riêng — `evidence_file` + `line_range` đã có sẵn trong facts sau
bất kỳ lượt `traverse` nào, và là đường dẫn **tương đối** (tốt hơn `defined_in` cũ vốn trả
đường dẫn tuyệt đối).
**Đáp án phải có:** đường dẫn file + khoảng dòng; `citation_verified=false` thì nói rõ
trích dẫn **chưa được kiểm** — nêu **một lần**, không lặp từng dòng.
**Thiếu năng lực:** `defined_in` đang trả **đường dẫn tuyệt đối** `/Users/…` dù
`asset_service.py:9` có `relative_to_ingest_root` — rò cấu trúc máy local. Trạng thái: —

---

# Tổng hợp đề xuất sửa/thêm tool

Không đề xuất tool mới nào — mọi năng lực thiếu đều nhét được vào tool sẵn có.

| # | Thay đổi | Phục vụ | Giá phải trả |
| --- | --- | --- | --- |
| 1 | `LineageEvidence` + `filter_condition`, `join_condition`; parser và LLM cùng trích lúc ingest; `traverse` trả về luôn | **C4 và C5** | Không tăng số tool, không cần định tuyến. **Phải xoá đồ thị rồi ingest lại toàn bộ** |
| 2 | ~~PK/FK~~ **— bỏ**, không có nguồn dữ liệu (0 constraint trong `samples/`). C5 đi chung cơ chế với C4 ở mục 1 | **C5** | Không tốn gì thêm ngoài mục 1 |
| 3 | `traverse.depth` mặc định **2** (thay `None` = vô hạn), thêm setting | **C1 C3 D1 D2** | Rủi ro hồi quy C1 (đang 1.00) — phải đo riêng |
| 4 | Facts gộp cạnh theo `(source, target, hops)` | **C1 C3 D1 D2** | Đổi hình dạng facts → test đang khẳng định hình cũ phải sửa theo |
| 5 | Facts thêm `no_facts` + rule hỏi lại | **H1** | Nhỏ |
| 6 | Rule "câu hỏi định nghĩa thì dừng ở định nghĩa" | **B1** | Nhỏ |
| 7 | `guard._fact_identifiers` đọc thêm `filter_condition`, `join_condition` | **C4, C5** — bắt buộc đi kèm #1 | Bỏ quên thì cột chỉ có trong điều kiện lọc sẽ bị `verify_node` báo bịa |

Không đề xuất: tool `read_definition` riêng (thành tool thứ 11 — xem §R1).

---

# Rủi ro đã biết, ảnh hưởng nhiều pattern

**R0 — Agent render dữ kiện chứ không suy luận. Đây là gốc của R3/R4.** Prompt compose
có **43 mệnh lệnh**; chỗ duy nhất nhắc `question` như chỉ thị là *"Answer in the same
language as the question"* — quy định về **ngôn ngữ**, không phải nội dung. 42 mệnh lệnh
còn lại đều dạng *"When <field> is present, state <field>"*. Không mệnh lệnh nào bảo model
chọn dữ kiện nào trả lời được câu hỏi, cũng không bảo nó trả lời.

Và `compose_node` gọi LLM với đúng hai message — system prompt + `"Question: … Facts: {json}"`;
`state["messages"]` **không bao giờ** được truyền. Model chọn tool biết mình đang tìm gì;
model viết câu trả lời không biết. Ý định mất ở ranh giới đó, dù `state["steps"]` đã lưu
sẵn `tool` + `args`.

Giải thích được cả bốn triệu chứng: có 16 cạnh thì in đủ 16 (C3); hỏi "là gì" mà sẵn fact
lineage thì in luôn (B1); facts không chứa `WHERE` thì in thứ đang có và **không nhận ra
mình chưa trả lời** (C4); không có fact nào thì **bịa** (H1).

**R1 — Bão hoà tool.** Ở **10 tool**, C2 rơi 1.00 → **0.20**; ba cấu hình **9 tool** khác
nhau đều phục hồi **1.00**. Thêm tool cho pattern mới có thể làm hỏng pattern đang chạy
tốt. Phạm vi: chỉ C2 lật, 4/6 case còn lại vẫn 1.00 ở 10 tool — **không** được đọc thành
"10 tool là hỏng". Hệ quả thực hành: mọi thay đổi `REGISTRY` phải đo lại **toàn bộ** bộ case.

**R1b — Agent chỉ thấy bản rút gọn giữa các lượt tool.** `agent_node` có nhận đủ
`state["messages"]` nên không mù, nhưng `ToolMessage` chứa `_summary(result)` —
*"small, safe tool payload"* theo đúng docstring. `traverse` chỉ còn **tên bảng** (không
cột, không biểu thức, không hop); `get_asset` chỉ còn `name/last_modified/modified_count/
is_defined`. Agent quyết định "gọi gì tiếp" trên bấy nhiêu — không suy luận được theo
**nội dung**. Đây là đánh đổi có lý do (chặn nhắc lại dữ liệu thô), không phải lỗi.

**R1c — Tóm tắt mang danh tính, không mang nội dung.** Mọi `_summary` đều trả tên/số
đếm/cờ; chỉ `breaking_changes` có một trường nội dung (`suggested_action`). Đo trên bộ case:

| Case | Câu hỏi hỏi gì | Tóm tắt mang gì | Kết quả |
| --- | --- | --- | --- |
| 01 (C1) | **tên bảng** nguồn | tên bảng ✓ | **1.00** |
| 04 (C2) | **công thức** tính cột | tên bảng — `transform_expression` **vắng** | **0.20** |
| 05 (G1) | bảng/cột nguồn của query | `source_table`, `source_column` ✓ | **1.00** |
| 02 (F1) | bảng bị drop/rename | `table_name`, `new_name`, `downstream_tables`, `suggested_action` ✓ | **1.00** |

Case 01 và 04 gọi **cùng một tool** — khác nhau ở chỗ tóm tắt có khớp hình dạng đáp án hay
không. Nên: pattern hỏi **"cái nào / ở đâu"** (A1 A2 C1 D1 E5 F1 G1) thì tóm tắt đủ; pattern
hỏi **"như thế nào / quy tắc gì / công thức gì / khoá nào"** (B1 B2 C2 C4 C5 D2 I1 I2) thì
**không đủ** — agent không biết mình đã trả lời được chưa nên dừng sớm.

Giá để bù đã đo: thêm `transform_expression` vào tóm tắt `traverse` tốn **+33 ký tự**
(288 → 321) ở ca có `column`.

**R2b — `search_column_description` chỉ tìm được ~16% số cột, và không báo khi trượt.**
*(Thay chẩn đoán R2 cũ — xem dưới.)* Tool tìm theo **ngữ nghĩa trên mô tả cột đã lưu**. Đo
trên đồ thị: **70** cặp `(bảng, cột)`, ước lượng chỉ **~11** cặp có mô tả. Với 84% còn lại
nó trả hàng xóm gần nhất như thể đã tìm thấy:

```
query='amount_paid'        -> stg_invoices.amount_paid       (khop chinh xac)
query='projected_revenue'  -> amount_billed, amount_paid, gender   (KHONG lien quan)
```

`projected_revenue` có thật trên `revenue_alerts_final` và `revenue_alerts_staging` — chỉ là
không có mô tả cột.

Đây là **gốc thật của C2** (case 04): model chọn tool hợp lý, nhận về ba cột lạ, không có bảng
để gọi `traverse`, rồi hết lượt. Và **E1** (case 03) chạy được chỉ vì `amount_paid` tình cờ
**có** mô tả. Cùng một cơ chế, khác nhau ở chỗ dữ liệu mô tả có hay không.

**Chẩn đoán cũ đã rút:** các bản trước ghi *"tool này hút nhầm câu hỏi cấp cột"*. Sai — model
chọn nó là hợp lý; tool mới là thứ trả lời không trung thực.

**R2 — `search_column_description` từng là tool chết, và đó là LỖI *(đã vá ở T-0b)*.** `_summary` không có nhánh
cho khoá `columns`, nên tool này rơi xuống nhánh mặc định hình dạng `traverse`, đọc
`result.confirmed` (rỗng) và báo về:

```json
{"ok": true, "confirmed": {"count": 0, "tables": []}, "pending": {"count": 0, "tables": []}}
```

Đo thật: `search_column_description(query='projected revenue')` trên `database_id=1` tìm
được **11 cột**. Agent được báo **`count: 0`**. Và khoá `columns` **không tồn tại** trong
`_facts`, nên kết quả cũng không tới được compose. Đóng góp duy nhất còn lại là bơm tên
vào `vocabulary` cho guard.

Đây đúng tool mà model với tay tới ở **C2** và **E1** — hai pattern hỏng nặng nhất. Hai
rủi ro khớp nhau: R1 (bão hoà) khiến model **chọn** nó; R2 khiến sai lầm thành **không
cứu được** — nhận tín hiệu "thành công, không có gì" rồi dừng. *(Chưa chứng minh vá R2 sẽ
chữa được C2/E1 — cổng eval vẫn đòi `must_call`. Nhưng hiện model không có tín hiệu nào
để đi tiếp.)*

**R2c — Tool rỗng từng trả rỗng thay vì báo rỗng.** Cùng một hình: tool được gọi, trả về
không có gì, **không báo lỗi**, model tưởng đã tra xong rồi dừng.

| Lần | Tool | Vì sao rỗng | Hậu quả đo được |
| --- | --- | --- | --- |
| F17 | `search_column_description` | `_summary` thiếu nhánh `columns` → báo `ok:true, count:0` | Case 03/04 hỏng, **eval vẫn báo pass** |
| R2b | `search_column_description` | ~84% cột không có mô tả | Gốc thật của C2 |
| r10 | `search_sql_content` | `count_searchable_sql_documents = 0` | Case 02 và 04 hỏng **3/3**; rút khỏi REGISTRY thì `tool_micro_average` 0.75 → **0.917** |

**Trạng thái:** M-7 đã sửa nhánh chỉ mục rỗng: `search_sql_content`,
`search_by_description` và semantic fallback của `search_column_description` kiểm index
**theo `database_id` lúc chạy**, trước khi gọi embedding. Rỗng → `error="index_empty"`, khác
hẳn "đã tra và không thấy gì". Nhánh exact-column vẫn đọc trực tiếp từ graph, không phụ thuộc
index mô tả.

**R3 — Prompt compose là bảng kê khai bắt buộc.** ~5.000 ký tự, hàng chục rule "khi có X
thì phải nêu X"; câu `Be concise` duy nhất nằm ở **cuối**. Đây là gốc của lê thê ở
B1/C1/C3/C4.

**R4 — Facts phẳng, không gộp.** Mỗi cạnh-cột là một entry lặp `source`/`target`; và
`raw_sql` bị loại khỏi facts nên C4 vô phương trả lời đúng.

---

# Độ dài câu trả lời — số nền

Từ `logs/chat-traces/*.jsonl`, **565 lượt** thật:

| Pattern | Câu hỏi | n | median | max |
| --- | --- | --- | --- | --- |
| C4 | `underperforming_doctors được lấy như nào` | 1 | **5.319** | 5.319 |
| B1 | `underperforming_doctors là gì` | 1 | 3.402 | 3.402 |
| C1 | `department_revenue lấy dữ liệu từ đâu?` | 49 | 2.465 | 8.695 |
| C1 | `revenue_alerts_final lấy dữ liệu từ đâu?` | 60 | **2.011** | 3.546 |
| C2 | `projected_revenue tính thế nào?` | 150 | 1.448 | 3.583 |
| G1 | `Query này lấy dữ liệu từ đâu? SELECT…` | 40 | 1.316 | 4.859 |
| E5 | `Nếu deploy DROP TABLE…` | 30 | 1.096 | 1.672 |
| F1 | `revenue_alerts_staging bị lỗi, tại sao?` | 113 | 1.002 | **15.167** |
| E1 | `xoá amount_paid thì vỡ gì?` *(đang hỏng)* | 88 | 127 | 4.119 |

Toàn thể: n=565, median 1.226, max 15.167.

**Ngắn không phải mục tiêu tự thân** — `xoá amount_paid thì vỡ gì?` chỉ dài 127 ký tự vì
**trả lời sai**. Mọi ngưỡng độ dài chỉ áp cho câu trả lời đã đúng.

# Độ phủ eval

8/34 pattern có case eval: C1, C2, C4, C5, E1, E5, F1, G1.
Chưa có case: toàn bộ A, B, D, H, I, và C3, C4, C5, E2–E4, F2, G2–G3.
