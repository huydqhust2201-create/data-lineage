# Prompt v2 vs v3 — so sánh thực nghiệm trên bộ `hospital`

> Corpus: 10 file `samples/hospital/models/**` mà parser tĩnh (sqlglot) fail → đi LLM fallback
> Model: `openai/gpt-4o-mini` · Dialect: `postgres` · Temperature: `0.0` · Runs: 2
> Ngày: 2026-08-28 · Script: `scratchpad` (`v2_vs_v3_hospital.py`), raw: `v2_vs_v3_raw.json`
> Prompt v2 lấy từ `git show d72de8f~1:src/services/_llm_prompt_v2.txt`; v3 = `src/services/_llm_prompt_v3.txt` hiện tại.

---

## 1. Verdict

**Phiên bản prompt KHÔNG phải nguyên nhân của việc "biển HITL".** Ở `confidence_threshold = 0.8`
(mặc định hiện tại), **cả v2 lẫn v3 chỉ tự-duyệt ~10%** số cạnh LLM; ở `0.5` thì **cả hai tự-duyệt
~99%**. Đòn bẩy là **ngưỡng**, không phải prompt.

**Nên giữ prompt v3.** Column-level là yêu cầu sản phẩm (trả lời "sửa/xoá **cột**"), v3 bắt được
rename cột mà v2 (table-level) không biểu diễn được, và recall của hai bản bằng nhau (1.00). Chênh
lệch auto-confirm giữa hai bản (3 vs 4 cạnh trên 20 file-run) nằm trong khoảng nhiễu.

---

## 2. Số liệu tổng hợp (2 run × 10 file)

| | v2 (table-level) | v3 (column-level) |
| --- | ---: | ---: |
| Cạnh sinh ra (sau dedup) | 30 | 41 (+37%) |
| **Ngưỡng 0.8** → tự-duyệt / HITL | **3 / 27** (10% auto) | **4 / 37** (10% auto) |
| **Ngưỡng 0.5** → tự-duyệt / HITL | **30 / 0** (100% auto) | **40 / 1** (98% auto) |
| Table-level vs ground-truth | P=1.00 R=1.00 F1=1.00 | P=0.97 R=1.00 F1=0.98 |
| Phân bố `resolution_method` | branch 14, ref_source 13, static 3 | branch 25, ref_source 11, static 4, dynamic 1 |

Ground-truth = hợp (union) các bảng nguồn qua **mọi nhánh** Jinja `if/else`/`for`, target = tên file.
15 cạnh table-level cho 8 file có lineage thật; 2 file (`department_alerts`, `monthly_lab_summary`)
đúng ra phải trả `unresolved` (tên bảng động).

---

## 3. Phát hiện

### 3.1. Ở ngưỡng 0.8, cả hai prompt đều "ngập" HITL — ở 0.5 thì cả hai sạch

`RESOLUTION_CONFIDENCE` (chung cho v2 và v3, không đổi): `static 0.90 / ref_source 0.70 / branch 0.50
/ dynamic 0.40 / macro 0.35 / speculative 0.25`. **Chỉ `static` vượt được ngưỡng 0.8.** Nhưng 8 file
fallback đều là Jinja `{% if %}`/`{% for %}` — nhánh có `{{ ref() }}` được gán `ref_source` (0.70),
nhánh bảng trần được gán `branch` (0.50) — **không cái nào ≥ 0.8**. Đây trùng khớp với
`llm_extraction_threshold_study.md`: *"0.8 is on the wrong side of the model's modal
confidence"*.

### 3.2. v3 nhiều HITL hơn về **số tuyệt đối** vì cạnh mịn hơn, không phải vì kém hơn

v3 sinh 41 cạnh vs v2 30 cạnh cho cùng phụ thuộc, do tách theo cột. Cùng ground-truth, cùng recall
1.00. Queue HITL của v3 *trông* to hơn nhiều nhưng đó là **chi tiết mức cột**, không phải lỗi.

### 3.3. Các cạnh `static` (0.9) đến từ **tên bảng trần trong nhánh `else`**, ở CẢ HAI bản, và không ổn định

| File | v2 | v3 |
| --- | --- | --- |
| `revenue_alerts_final` → `manual_finance_review_queue` | run0: `static` 0.9 · run1: `branch` 0.5 | run0: `branch` 0.5 · run1: `static` 0.9 |
| `underperforming_doctors` → `hr_review_flagged_staff` | run0+run1: `static` 0.9 | run0: `branch` 0.5 · run1: `static` 0.9 |

Model đọc `FROM hr_review_flagged_staff` (bảng vật lý, không `ref()`, không động) = `static` — và
phần lớn bỏ qua việc nó nằm trong `{% if %}`. Nhãn **đảo giữa các run** ở cả hai prompt. Đây không
phải điểm mạnh của v2; đó là nhiễu + overconfidence chung.

### 3.4. v3 bắt được rename cột mà v2 không biểu diễn được

`revenue_alerts_staging.sql` nhánh else: `SELECT department_id, total_revenue AS projected_revenue
FROM {{ ref('department_revenue') }}`.

- v2 (cả 2 run): `department_revenue → revenue_alerts_staging` (table-level, mất thông tin cột).
- v3 (cả 2 run): `department_revenue.total_revenue → revenue_alerts_staging.projected_revenue`
  (`ref_source` 0.7) — **giữ được rename**, đúng cái Impact Analysis cần để cảnh báo "cột đích lấy
  từ cột nguồn tên khác".

### 3.5. v3 có 1 false-positive; ngưỡng ≥ 0.5 tự lọc

`monthly_lab_summary` (tên bảng `stg_lab_results_` + hậu tố runtime): v2 trả `unresolved` sạch cả 2
run. v3 run0 đoán `stg_lab_results_ → monthly_lab_summary` ở `dynamic` (0.40) — sai, nhưng
confidence thấp nên **rơi vào HITL** ở mọi ngưỡng ≥ 0.5. v3 run1 trả `unresolved` như v2.

### 3.6. Recall = 1.00 cho cả hai

Không bản nào bỏ sót nhánh Jinja. Mọi bảng nguồn của mọi nhánh đều được liệt kê, cả 2 run.

---

## 4. Hạn chế

1. **n = 2 run.** Đủ để thấy `temperature=0.0` không tất định (nhãn `static`/`branch` đảo), không đủ
   để ước lượng phương sai.
2. **Corpus 10 file, ground-truth do team tự viết** — đo mức đồng thuận với nhãn của chính mình, giống
   caveat của threshold study.
3. **1 model, 1 dialect, 1 project.** `gpt-4o-mini` / postgres / hospital. Chưa test cross-file macro,
   package dependency, file dài.
4. **`transform_type` không ổn định** (khớp với threshold study §4) — không dùng trong P/R ở đây.
5. Chỉ đo trên tập **parser fail**. Toàn bộ pipeline hospital: 54 cạnh parser (P/R chưa đo lại ở v3) +
   ~18 cạnh LLM pending.

---

## 5. Khuyến nghị

1. **Hạ `confidence_threshold` 0.8 → 0.5** (`src/config.py`). Đây là quyết định team (shared config).
   Đã được `llm_extraction_threshold_study.md` khuyến nghị độc lập. Ở 0.5: `static`/`ref_source`/
   `branch` tự duyệt, chỉ `dynamic`/`macro`/`speculative` (≤ 0.40) vào HITL — đúng bản chất triage.
2. **Giữ prompt v3.** Không quay lại v2.
3. **Chạy lại `eval/run_extraction_eval.py` với prompt v3** để có P/R headline hiện tại (report.md
   đang báo số đo trên v2).
4. **Cân nhắc**: gán `static` cho "tên bảng trần trong nhánh Jinja có điều kiện" là hơi lỏng — có thể
   thêm rule prompt: nếu bảng nằm trong `{% if %}`/`{% for %}` thì trần cấp nhất là `branch`.
