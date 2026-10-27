CREATE TABLE stg_admissions AS (
    WITH source AS (
        SELECT * FROM raw_admissions
    )
    SELECT
        admission_id,
        patient_id,
        ward,
        admitted_at,
        discharged_at
    FROM source
);
