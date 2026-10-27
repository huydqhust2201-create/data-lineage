-- Hop cuối của chuỗi: raw_patients -> stg_patients -> patient_visit_summary
-- -> patient_risk_score -> readmission_flag (5 node liên tiếp).
CREATE TABLE readmission_flag AS (
    WITH risk AS (
        SELECT * FROM patient_risk_score
    )
    SELECT
        risk.patient_id,
        risk.total_admissions,
        risk.abnormal_lab_count
    FROM risk
    WHERE risk.total_admissions >= 2
);
