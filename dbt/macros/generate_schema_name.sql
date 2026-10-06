{# Usa el schema configurado tal cual (staging, intermediate, marts) en vez de public_staging. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name else target.schema }}
{%- endmacro %}
