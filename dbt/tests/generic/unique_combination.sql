{# Combinación de columnas única (como dbt_utils.unique_combination_of_columns, sin dependencia externa). #}
{% test unique_combination(model, columns) %}
select {{ columns | join(', ') }}, count(*)
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}
