-- Bảng lab tổng hợp theo tháng: tên bảng nguồn có tiền tố cố định nhưng hậu
-- tố (tháng chạy job) chỉ biết lúc runtime -> parser tĩnh không đọc được,
-- nhưng LLM vẫn suy luận được nguồn hợp lý từ phần tiền tố literal rõ ràng
-- (rubric: "straightforward concatenation" -> confidence 0.7, vẫn dưới
-- threshold 0.8 nên phải qua HITL).
EXECUTE IMMEDIATE
    'INSERT INTO monthly_lab_summary SELECT patient_id, COUNT(*) AS abnormal_count '
    || 'FROM stg_lab_results_' || TO_CHAR(CURRENT_DATE, 'YYYYMM')
    || ' WHERE is_abnormal = TRUE GROUP BY patient_id';
