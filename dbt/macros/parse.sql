{# Número en cualquiera de los tres formatos de la descarga masiva: 123, 1234,5 y 1,4e+07.
   Lo que no calza queda null; el test `valores_no_parseados` lo detecta. #}
{% macro to_num(expr) -%}
    case when {{ expr }} ~ '^-?[0-9]+(,[0-9]+)?(e[+-]?[0-9]+)?$'
         then replace({{ expr }}, ',', '.')::numeric end
{%- endmacro %}

{# Fecha AAAA-MM-DD; '1900-01-01' es el centinela de "sin fecha". #}
{% macro to_fecha(expr) -%}
    case when {{ expr }} ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' and left({{ expr }}, 10) <> '1900-01-01'
         then left({{ expr }}, 10)::date end
{%- endmacro %}

{# Columna cuyo nombre cambió entre épocas (con y sin tildes). #}
{% macro col(data, names) -%}
    coalesce({% for n in names %}{{ data }} ->> '{{ n }}'{{ ", " if not loop.last }}{% endfor %})
{%- endmacro %}
