CREATE TABLE patient_risk_score AS (
    WITH visits AS (
        SELECT * FROM patient_visit_summary
    ),
    labs AS (
        SELECT * FROM stg_lab_results
    )
    SELECT
        visits.patient_id,
        visits.total_admissions,
        visits.total_appointments,
        COUNT(CASE WHEN labs.is_abnormal THEN 1 END) AS abnormal_lab_count
    FROM visits
    LEFT JOIN labs ON visits.patient_id = labs.patient_id
    GROUP BY visits.patient_id, visits.total_admissions, visits.total_appointments
);
