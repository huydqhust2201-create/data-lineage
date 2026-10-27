-- Cảnh báo theo khoa: bảng nguồn được chọn ĐỘNG lúc runtime tuỳ tham số job
-- scheduler truyền vào, không cố định lúc viết SQL -> parser tĩnh không đọc
-- được, phải rơi xuống LLM fallback (FR-3), và vì nguồn chỉ suy luận được
-- qua tên biến chứ không phải literal, LLM nên gán confidence thấp -> cạnh
-- này phải rơi vào hàng đợi HITL (FR-4), không được tự động ghi vào graph.
EXECUTE IMMEDIATE
    'INSERT INTO department_alerts SELECT * FROM ' || target_summary_table
    || ' WHERE total_revenue < revenue_threshold';
