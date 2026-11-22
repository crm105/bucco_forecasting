{% docs season %}
The MLB season (calendar year) the row describes.
{% enddocs %}

{% docs team_id %}
MLB Stats API team id. This is the franchise key for the whole project. The id stays the same
through moves and renames (the Expos and Nationals are both 120, the Devil Rays and Rays both
139), so one id is one franchise across every season.
{% enddocs %}

{% docs wins %}
Regular-season wins. Counts a tiebreaker game when one was played.
{% enddocs %}

{% docs losses %}
Regular-season losses. Counts a tiebreaker game when one was played.
{% enddocs %}

{% docs games_played %}
Regular-season games played (wins plus losses). Usually 162, but a few games a year are rained
out and never made up, so 161 shows up. A tiebreaker game can make it 163.
{% enddocs %}

{% docs win_pct %}
Wins divided by wins plus losses, from 0 to 1. Models predict this rather than a win count, so
a shortened season such as 2020 (60 games) doesn't need special handling. Multiply by 162 to
show it as wins.
{% enddocs %}

{% docs is_shortened_season %}
True when the team played fewer than `full_season_min_games` (150) games. Only 2020 in the
current history. Win percentage from a shortened season is a noisier signal of team quality.
{% enddocs %}

{% docs as_of_date %}
The date a projection was published or captured. A projection can only be used to forecast a
season if this date is on or before that season's Opening Day.
{% enddocs %}
