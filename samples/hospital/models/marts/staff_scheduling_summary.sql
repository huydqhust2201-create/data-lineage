-- Cạnh đi VÀO bảng này sẽ là pending (Jinja if/else, LLM suy luận) — dùng để
-- bạn tự bấm "Xác nhận" trên UI và quan sát hiệu ứng mở khoá.
{% if var('use_contractor_roster', false) %}
SELECT doctor_id, department_id
FROM contractor_roster
{% else %}
SELECT doctor_id, department_id
FROM {{ ref('stg_doctors') }}
{% endif %}
