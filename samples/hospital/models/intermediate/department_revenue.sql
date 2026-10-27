-- Fan-in cố ý từ 3 nguồn khác nhau (invoices, appointments, doctors) — dùng để
-- minh hoạ impact analysis lan toả > 3 node khi 1 trong 3 nguồn này đổi.
CREATE TABLE department_revenue AS (
    WITH invoices AS (
        SELECT * FROM stg_invoices
    ),
    appts AS (
        SELECT * FROM stg_appointments
    ),
    doctors AS (
        SELECT * FROM stg_doctors
    )
    SELECT
        doctors.department_id,
        doctors.department_name,
        SUM(invoices.amount_paid) AS total_revenue,
        COUNT(DISTINCT appts.appointment_id) AS total_appointments
    FROM invoices
    JOIN appts ON invoices.patient_id = appts.patient_id
    JOIN doctors ON appts.doctor_id = doctors.doctor_id
    GROUP BY doctors.department_id, doctors.department_name
);
