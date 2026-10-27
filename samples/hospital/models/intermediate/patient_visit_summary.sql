CREATE TABLE patient_visit_summary AS (
    WITH patients AS (
        SELECT * FROM stg_patients
    ),
    appts AS (
        SELECT * FROM stg_appointments
    ),
    admits AS (
        SELECT * FROM stg_admissions
    )
    SELECT
        patients.patient_id,
        patients.patient_name,
        COUNT(DISTINCT appts.appointment_id) AS total_appointments,
        COUNT(DISTINCT admits.admission_id) AS total_admissions,
        MAX(admits.discharged_at) AS last_discharge_at
    FROM patients
    LEFT JOIN appts ON patients.patient_id = appts.patient_id
    LEFT JOIN admits ON patients.patient_id = admits.patient_id
    GROUP BY patients.patient_id, patients.patient_name
);
