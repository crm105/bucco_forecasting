{#
  How long each player spent on the injured list (disabled list before 2019) in each regular
  season, from 2009: days, stints and whether any was on the 60-day list. A stint runs from its
  placement (the retroactive date when there is one) to the player's next activation, or to the
  season's last game if none; days are counted once each within the regular season (first to
  last scheduled game), so a stint begun in spring training counts from Opening Day, and
  duplicated or overlapping entries (2021 lists some placements twice and records moves to the
  60-day list as new placements, without retroactive dates) cannot double-count. A player
  released or traded while on the list counts to his next activation anywhere, or season's end.
  Players never on the list have no row. Features for our playing-time models.
#}

with tx as (

    select * from {{ ref('stg_mlb__il_transactions') }}

),

bounds as (

    select season, min(game_date)::date as first_day, max(game_date)::date as last_day
    from {{ ref('stg_mlb__schedules') }}
    group by season

),

placed as (

    select
        tx.season,
        tx.mlbam_id,
        coalesce(least(tx.retro_date, tx.effective_date), tx.effective_date) as start_day,
        tx.list_days
    from tx
    where tx.event = 'placed'

),

sixty as (

    -- placed on the 60-day list, or moved to it from a shorter one
    select distinct season, mlbam_id
    from tx
    where (event = 'placed' and list_days = 60)
       or (event = 'transferred' and regexp_matches(description, 'to the 60[- ]day', 'i'))

),

stints as (

    select
        placed.season,
        placed.mlbam_id,
        placed.start_day,
        placed.list_days,
        coalesce((select min(a.effective_date) from tx as a
                  where a.mlbam_id = placed.mlbam_id and a.event = 'activated'
                    and a.effective_date > placed.start_day), date '2100-01-01') as end_day
    from placed

),

clipped as (

    select
        stints.season,
        stints.mlbam_id,
        stints.list_days,
        greatest(stints.start_day, bounds.first_day)                       as start_day,
        least(stints.end_day - 1, bounds.last_day)                         as end_day
    from stints
    inner join bounds on bounds.season = stints.season

),

days as (

    select season, mlbam_id, unnest(generate_series(start_day, end_day, interval 1 day)) as day
    from clipped
    where end_day >= start_day

)

select
    stints.season,
    stints.mlbam_id,
    coalesce(d.il_days, 0)                                                 as il_days,
    count(*)                                                               as il_stints,
    max(case when sixty.mlbam_id is not null then 1 else 0 end)            as on_60_day
from clipped as stints
left join sixty on sixty.season = stints.season and sixty.mlbam_id = stints.mlbam_id
left join (select season, mlbam_id, count(distinct day) as il_days from days group by 1, 2) as d
    on d.season = stints.season and d.mlbam_id = stints.mlbam_id
group by stints.season, stints.mlbam_id, d.il_days
