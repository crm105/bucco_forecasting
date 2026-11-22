-- The clinch indicator is how playoff status is derived, so check it against the number of
-- playoff teams each era actually had: 8 before 2012, 10 from 2012 to 2019, 16 in 2020,
-- 10 in 2021, and 12 from 2022. Add a rule here if MLB changes the format again.

with counts as (

    select
        season,
        count(*) filter (where made_playoffs) as playoff_teams
    from {{ ref('team_seasons') }}
    group by season

),

expected as (

    select
        season,
        playoff_teams,
        case
            when season = 2020 then 16
            when season >= 2022 then 12
            when season = 2021 or season between 2012 and 2019 then 10
            else 8
        end as expected_teams
    from counts

)

select * from expected
where playoff_teams <> expected_teams
