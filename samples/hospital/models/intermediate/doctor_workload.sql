CREATE TABLE doctor_workload AS (
    WITH doctors AS (
        SELECT * FROM stg_doctors
    ),
    appts AS (
        SELECT * FROM stg_appointments
    )
    SELECT
        doctors.doctor_id,
        doctors.doctor_name,
        doctors.department_name,
        COUNT(appts.appointment_id) AS appointment_count
    FROM doctors
    LEFT JOIN appts ON doctors.doctor_id = appts.doctor_id
    GROUP BY doctors.doctor_id, doctors.doctor_name, doctors.department_name
);
