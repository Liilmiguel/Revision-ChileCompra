{# Valores dentro de [min_value, max_value] (como dbt_utils.accepted_range, sin dependencia externa). #}
{% test accepted_range(model, column_name, min_value, max_value) %}
select {{ column_name }} from {{ model }}
where {{ column_name }} < {{ min_value }} or {{ column_name }} > {{ max_value }}
{% endtest %}
