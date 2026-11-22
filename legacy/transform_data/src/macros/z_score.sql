
{% macro z_score(column, partition_col) %}

({{ column }} - AVG({{ column }} ::FLOAT) OVER (PARTITION by {{ partition_col }}) ) /
    stddev({{ column }}) OVER(partition by {{ partition_col }})

{% endmacro %}
