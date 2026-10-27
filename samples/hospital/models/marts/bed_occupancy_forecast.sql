-- Cả 2 nhánh đều là tên bảng trần (không qua ref()/source()), tuỳ feature
-- flag "use_ward_level_forecast" chọn lúc runtime -> LLM chỉ suy luận được
-- qua tên gọi (rubric: "naming inference" -> confidence 0.5).
{% if var('use_ward_level_forecast', true) %}
SELECT ward, COUNT(*) AS occupied_beds
FROM patient_visit_summary
GROUP BY ward
{% else %}
SELECT department_name AS ward, COUNT(*) AS occupied_beds
FROM department_capacity_snapshot
GROUP BY department_name
{% endif %}
