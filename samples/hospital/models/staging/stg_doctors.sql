CREATE TABLE stg_doctors AS (
    WITH source AS (
        SELECT * FROM raw_doctors
    ),
    dept AS (
        SELECT * FROM raw_departments
    )
    SELECT
        source.doctor_id,
        source.full_name AS doctor_name,
        dept.department_id,
        dept.department_name
    FROM source
    JOIN dept ON source.department_id = dept.department_id
);
