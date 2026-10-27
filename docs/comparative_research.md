# So sánh: nội bộ (parser vs LLM vs hybrid) + với công cụ lineage khác

> Bổ sung cho [`PRD.md`](PRD.md) mục 3 (Success Metrics) và mục 10 (Risks) — đặc biệt trả lời rủi ro đã tự ghi nhận từ đầu dự án: *"Ngưỡng confidence 0.8 chưa có cơ sở thực nghiệm... Đo precision/recall theo từng ngưỡng trong `eval/`, điều chỉnh sau"* (PRD.md mục 10).

## 1. So sánh nội bộ: parser-only vs LLM-only vs hybrid (số liệu thật)

Chạy `eval/run_pipeline_eval.py` với `--mode {hybrid,parser_only,llm_only}` trên cùng 1 corpus (`tests/ground_truth/sql/`, 13 fixture, gồm cả case `13_saas_analytics_pipeline` — 9 statement CTE/window function/CASE WHEN/UNION ALL — mới thêm để có case đủ phức tạp). Chi tiết đầy đủ: [`eval/results/pipeline_eval.md`](../eval/results/pipeline_eval.md) (hybrid — đúng luồng agent thật), [`pipeline_eval_parser_only.md`](../eval/results/pipeline_eval_parser_only.md), [`pipeline_eval_llm_only.md`](../eval/results/pipeline_eval_llm_only.md).

| Mode | Precision | Recall | F1 | Đạt PRD (≥0.80 cả hai)? |
|---|---:|---:|---:|:---:|
| **Hybrid** (parser trước, LLM fallback chỉ khi parser rỗng — production thật) | 0.92 | 0.95 | 0.94 | ✅ |
| **Parser-only** (bỏ hẳn LLM fallback) | 0.92 | 0.95 | 0.94 | ✅ |
| **LLM-only** (ép mọi file qua LLM, kể cả file parser đọc được) | 0.20 | 0.29 | 0.23 | ❌ |

### Nhận xét

1. **Parser-only = Hybrid trên corpus hiện tại.** 12/13 fixture parse tĩnh thành công; chỉ `07_dynamic_sql_fail.sql` (cố ý không parse được) cần LLM fallback, và ở fixture đó LLM cũng từ chối đoán (đúng thiết kế "prefer unresolved over guessing" trong prompt, xem `tests/ground_truth/README.md`) — nên LLM fallback hiện đóng góp **0 lợi ích ròng** trên corpus này. Đây không phải bằng chứng "LLM fallback vô dụng" — corpus ground-truth hiện có quá ít case "parser fail nhưng LLM cứu được"; cần bổ sung thêm case dạng đó để đo đúng giá trị thật của nhánh fallback.

2. **LLM-only thấp không phải vì LLM "hiểu SQL kém" — mà vì lệch quy ước đặt tên bảng đích.** Khi không có `CREATE TABLE`/`CREATE VIEW` tường minh (đa số fixture 01-12 là bare `SELECT` nhiều CTE), 2 kỹ thuật suy ra `target_table` theo 2 cách khác nhau:
   - **Parser tĩnh** (heuristic trong `parser_service.py`): dùng alias bảng/CTE đầu tiên trong `FROM` của SELECT cuối cùng (vd `top_sellers`, `joined`).
   - **LLM** (đúng theo rule trong chính prompt của nó — `_llm_prompt_v4.txt`): "dbt model file không có DML tường minh → target = tên file" (vd `08_olist_complex`).
   
   Ground truth hiện chỉ ghi theo quy ước của parser, nên khi LLM suy luận đúng theo quy ước RIÊNG của nó (không sai logic, chỉ khác convention), vẫn bị tính là "spurious". Đây là 1 phát hiện phương pháp luận thật (không phải bịa) — không kết luận được "LLM extraction kém" từ con số 0.20 này; muốn so sánh công bằng cần 1 bộ ground-truth riêng dùng toàn `CREATE TABLE/VIEW AS` (như `13_saas_analytics_pipeline.sql`) để cả 2 kỹ thuật có cùng 1 đích tường minh.

3. **Quét ngưỡng confidence (0.5→0.9) không đổi kết quả trên corpus hybrid/parser_only** — vì gần như toàn bộ cạnh đến từ parser (confidence=1.0 cố định), chỉ 1 fixture cần LLM và fixture đó không sinh cạnh nào. Ngưỡng 0.8 hiện tại **chưa bị bác bỏ nhưng cũng chưa được xác nhận có ý nghĩa** trên corpus này — cần thêm case "LLM extraction thành công với confidence trung bình" (vd giống `samples/complex_pipeline/llm_fallback_demo.sql`, đã verify LLM trích đúng với confidence 0.4 khi tên bảng là literal tĩnh trong SQL động) vào ground-truth để ngưỡng sweep thật sự có tín hiệu.

4. **Column-level precision/recall thấp hơn nhiều so với table-level** (xem section "Column-Level Micro-Average" trong `pipeline_eval.md`) — dự kiến, vì PRD chỉ ưu tiên table-level (`docs/brief.md` mục Key Features: "table-level là ưu tiên chính; column-level là mở rộng"); phần lớn fixture ground-truth cũ không khai báo `source_column`/`target_column`. Số liệu cột chỉ có ý nghĩa thật trên fixture có khai báo cột đầy đủ (vd `13_saas_analytics_pipeline.json`).

## 2. So sánh với công cụ lineage khác trên thị trường

**⚠️ Lưu ý quan trọng**: phần này dựa trên hiểu biết công khai về kiến trúc các công cụ dưới đây tại thời điểm viết (không gọi API/không truy cập trực tiếp hệ thống của họ trong lúc soạn tài liệu) — **khuyến nghị người đọc tự kiểm tra lại với tài liệu chính thức mới nhất của từng công cụ trước khi dùng cho tài liệu chính thức/pitch**, vì các sản phẩm này cập nhật tính năng liên tục.

| Trục so sánh | **Dự án này (P-116)** | OpenMetadata | DataHub | Atlan |
|---|---|---|---|---|
| Phương pháp trích xuất | Static parse SQL/dbt (sqlglot) là nguồn chính; LLM fallback CHỈ khi parser fail | Connector theo từng nguồn dữ liệu; với dbt, đọc `manifest.json` đã compile sẵn (không tự parse raw SQL) | Connector + ingestion framework; với SQL thường qua plugin phân tích query log/SQL (`sqllineage`-style) hoặc metadata warehouse cung cấp sẵn | Connector-based, layer lineage trên nền Atlas metadata model; kết hợp connector + lịch sử query |
| Cách xử lý độ tin cậy/không chắc chắn | Mỗi cạnh có `confidence` (1.0 parser / <1.0 LLM) + `LineageEvidence` (file, dòng, SQL gốc hoặc `reasoning`/`matched_text`/`resolution_method` cho cạnh LLM) — hiển thị tường minh cho người dùng | Thường coi lineage từ connector là xác định (deterministic), không gắn độ tin cậy dạng số | Tương tự — lineage từ ingestion pipeline coi là "đã xác nhận", không có khái niệm confidence-score-per-edge phổ biến | Tương tự các nền tảng enterprise khác — ít khi lộ độ tin cậy dạng số ra UI |
| Quy trình duyệt người (HITL) | Bắt buộc: mọi cạnh nguồn LLM phải qua `GET /pending-review` → `POST /pending-review/{id}/confirm|reject` trước khi vào đồ thị chính thức (`src/api/routes.py`) | Không có khái niệm "chờ duyệt trước khi ghi nhận" cho lineage — sửa tay sau khi đã ghi | Tương tự | Tương tự, một số bản enterprise có workflow governance riêng nhưng không phải cho từng cạnh lineage suy luận |
| Chi phí setup | Không cần connector riêng cho từng nguồn — chỉ cần đọc thư mục source code SQL/dbt, không cần kết nối warehouse thật | Cần cấu hình connector cho từng nguồn (warehouse, BI tool, orchestrator...), hạ tầng ingestion framework riêng | Tương tự OpenMetadata — cần triển khai ingestion framework (thường chạy qua Airflow/cron) | SaaS, enterprise — cần hợp đồng/license, connector do Atlan quản lý |
| Độ phủ SQL thô / non-dbt | Tốt — đọc trực tiếp file `.sql` bất kỳ (không bắt buộc phải là dbt project), tự tiền xử lý Jinja dbt cơ bản (`ref()`/`source()`/`config()`) | Phụ thuộc connector — mạnh nhất khi nguồn ĐÃ có metadata lineage sẵn (dbt manifest, warehouse system tables); SQL rời rạc không thuộc pipeline nào thường không được phủ | Tương tự — mạnh khi tích hợp trực tiếp warehouse/orchestrator, cần thêm cấu hình cho SQL rời rạc | Tương tự các nền tảng enterprise — tối ưu cho hệ sinh thái đã kết nối, không phải kịch bản "chỉ có 1 folder SQL" |

### Định vị

Dự án này **không cạnh tranh trực tiếp** với các nền tảng enterprise trên (không có UI catalog đầy đủ, không quản lý phân quyền doanh nghiệp — xem `PRD.md` mục Non-goals) — điểm khác biệt thật sự là: (1) không cần kết nối warehouse/connector nào, chỉ cần đọc source code SQL/dbt, phù hợp giai đoạn chưa có hạ tầng data platform đầy đủ; (2) mọi cạnh không chắc chắn đều tường minh về độ tin cậy VÀ bắt buộc người duyệt trước khi tin — giảm rủi ro "tin nhầm 1 lineage sai do AI suy luận" so với việc coi mọi kết quả ingestion là đã xác nhận.

## 3. Benchmark hiệu năng thật

Xem [`eval/results/performance_benchmark.md`](../eval/results/performance_benchmark.md) — số liệu ingest latency theo kích thước, chat turn latency (p50/p95), chi phí LLM thật (token usage thật × giá OpenRouter), và độ trễ impact-query theo kích thước đồ thị. Đo trên máy dev, dự án **chưa deploy** (README: "chưa deploy — kế hoạch W4-W5") nên đây không phải benchmark production thật.
