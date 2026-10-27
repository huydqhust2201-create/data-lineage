{% if var('flag_low_volume_doctors', true) %}
SELECT doctor_id, appointment_count
FROM {{ ref('doctor_workload') }}
WHERE appointment_count < 5
{% else %}
SELECT doctor_id, 0 AS appointment_count
FROM hr_review_flagged_staff
{% endif %}
