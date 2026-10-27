{% macro cents_to_dollars(column_name, scale=100) %}
    ({{ column_name }} / {{ scale }}::numeric)
{% endmacro %}
