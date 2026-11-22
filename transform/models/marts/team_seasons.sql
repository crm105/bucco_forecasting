{#
  Actual results: one row per team per completed season.

  This table holds what really happened. Only the backtest (evaluate/) should read it to
  score forecasts. Models get their inputs from team_season_features, which holds nothing
  from the season being forecast.
#}

select * from {{ ref('int__team_seasons') }}
