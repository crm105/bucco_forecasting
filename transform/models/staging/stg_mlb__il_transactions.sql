{#
  Injured-list transactions from the MLB Stats API, typed. One row per transaction.
#}

select
    cast(season as integer)                 as season,
    cast(transaction_id as bigint)          as transaction_id,
    cast(effective_date as date)            as effective_date,
    cast(retro_date as date)                as retro_date,
    cast(mlbam_id as bigint)                as mlbam_id,
    cast(team_id as integer)                as team_id,
    event,
    cast(list_days as integer)              as list_days,
    description
from {{ source('mlb_api', 'il_transactions') }}
