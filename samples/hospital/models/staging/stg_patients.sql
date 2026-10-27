CREATE TABLE stg_patients AS (
    WITH source AS (
        SELECT * FROM raw_patients
    )
    SELECT
        patient_id,
        full_name AS patient_name,
        date_of_birth,
        gender,
        insurance_provider
    FROM source
);
