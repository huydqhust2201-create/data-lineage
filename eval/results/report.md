# Evaluation Report

> Báo cáo đánh giá chất lượng sản phẩm theo tiêu chí BTC.

---

## 1. Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Extraction accuracy (Precision/Recall) | ≥80% cả hai | P=85%, R=85% (F1=85%) — [`pipeline_eval.md`](pipeline_eval.md), toàn bộ agent (parser + LLM fallback) trên `tests/ground_truth/sql/`, prompt LLM v2 | ✅ |
| Response latency | <3s | — | ⏳ |
| User satisfaction | >4/5 | — | ⏳ |
| Test coverage | >60% | — | ⏳ |

## 2. Test Results

### Unit Tests
```
pytest tests/ -v
# Paste output here
```

### Integration Tests
```
# Mô tả test scenarios và kết quả
```

### Manual Test Cases

6/6 PASS test trực tiếp trên **sản phẩm cuối** (frontend thật, click UI — không gọi API bằng tay), backend live thật (Postgres + LLM thật, không mock) — chi tiết từng case kèm ảnh chụp màn hình từng bước: [`manual_test_cases.md`](../manual_test_cases.md).

| Test ID | Test Case | Status |
|---|---|---|
| TC-01 | Ingest dbt project thật end-to-end | ✅ PASS |
| TC-02 | Impact analysis — downstream thật | ✅ PASS |
| TC-03 | Chatbot — câu hỏi tổng quát (regression) | ✅ PASS |
| TC-04 | Chatbot — phân biệt "0 downstream" vs "0 dữ liệu" (regression) | ✅ PASS |
| TC-05 | HITL Approve — pending → confirmed | ✅ PASS |
| TC-06 | HITL Reject — không lọt vào đồ thị, chặn xử lý trùng | ✅ PASS |

## 3. User Feedback

| User | Feedback | Rating |
|------|----------|--------|
| [User 1] | [feedback] | [1-5] |
| [User 2] | [feedback] | [1-5] |

## 4. Demo Results

- Ngày demo: [YYYY-MM-DD]
- Người tham gia: [số người]
- Feedback chung: [tóm tắt]
- Issues phát hiện: [danh sách]

## 5. Action Items

- [ ] Parser: `06_union_all` (CTE union 2 nhánh đều `SELECT *`) và `05_case_when` (gán nhầm bảng nguồn cột không tường minh) — 2 gap chưa fix, xem `eval/results/pipeline_eval.md`
- [ ] Prompt LLM v2 (so với v1): recall giảm trên 2 case đòi hỏi suy luận xuyên câu lệnh — `06_union_all` (chọn nhầm target = tên file thay vì CTE cuối `all_orders`) và `07_dynamic_sql_fail` (không nối được tham số `CALL proc('stg_orders', ...)` với procedure param, trả `unresolved` thay vì suy luận như v1) — có thể do prompt v2 nhấn mạnh "never invent" khiến model bảo thủ hơn ở case cần suy luận cross-statement. Cần Trường xem lại nếu muốn khôi phục recall cũ mà không mất độ an toàn chống hallucination.
