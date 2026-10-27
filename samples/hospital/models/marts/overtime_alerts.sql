-- File sạch (CTAS) -- sẽ cho cạnh CONFIRMED confidence 1.0 từ
-- staff_scheduling_summary. Trước khi bạn confirm cạnh pending phía trên,
-- bảng này hoàn toàn VÔ HÌNH khi hỏi /impact xuất phát từ stg_doctors.
CREATE TABLE overtime_alerts AS (
    WITH source AS (
        SELECT * FROM staff_scheduling_summary
    )
    SELECT
        doctor_id,
        department_id,
        TRUE AS flagged_for_review
    FROM source
);
