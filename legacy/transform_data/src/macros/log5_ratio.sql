{% macro log5_ratio(team_a_win_rate, team_b_win_rate) %}

({{ team_a_win_rate }} - ({{ team_a_win_rate }} * {{ team_b_win_rate }}))/
NULLIF(({{ team_a_win_rate }} + {{ team_b_win_rate }}  - (  2 *  {{ team_a_win_rate }} * {{ team_b_win_rate }})),0)

{% endmacro %}
