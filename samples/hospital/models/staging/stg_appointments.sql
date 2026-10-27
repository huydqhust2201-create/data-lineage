CREATE TABLE stg_appointments AS (
    WITH source AS (
        SELECT * FROM raw_appointments
    )
    SELECT
        appointment_id,
        patient_id,
        doctor_id,
        appointment_date,
        status
    FROM source
);
