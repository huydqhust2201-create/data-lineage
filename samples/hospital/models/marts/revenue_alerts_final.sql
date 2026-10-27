-- Cố ý nối tiếp NGAY SAU 1 cạnh pending khác (nguồn = revenue_alerts_staging,
-- bản thân nó cũng chỉ có nguồn pending) -> tạo chuỗi pending -> pending 2
-- tầng liên tiếp, để test xem impact có "đi xuyên" được 2 lớp không chắc
-- chắn hay dừng lại ngay ở lớp đầu.
{% if var('escalate_to_finance', true) %}
SELECT department_id, projected_revenue
FROM {{ ref('revenue_alerts_staging') }}
WHERE projected_revenue < 0
{% else %}
SELECT department_id, projected_revenue
FROM manual_finance_review_queue
{% endif %}
