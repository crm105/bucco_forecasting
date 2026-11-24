---
name: team-outlook
description: Build, refresh, review or revise the team outlook page (positions against the league, lineup, division, free-agent targets) for the Pirates or another team, from the lineup-optimized player-projection forecast. Use when the user asks for a season outlook, a strengths/weaknesses or free-agent report, a refresh after new projections, or changes to that page.
---

# Team outlook

The outlook explains one team's forecast position by position. It is fully generated:

- **Numbers:** `src/bucco/report/outlook_data.py` (lineup optimizer for batting, projections as given for pitching, free agents valued by re-optimizing the lineup).
- **Wording:** `config/outlook_text.yml` (templates with checked `{placeholders}`).
- **Page and charts:** `src/bucco/report/outlook_render.py`.
- **Command:** `uv run bucco outlook --team PIT [--model steamer_optimized] [--season 2027] [--as-of YYYY-MM-DD]`, which writes `reports/<season>/<model>_<team>_outlook_<as-of>.html`.

Never edit a generated HTML file: the next build overwrites it.

## Refresh after new projections

Run these in order, stopping on any error:

1. Put the new download in `data/manual/projections/` as `steamer_<batters|pitchers>_individual_<season>.csv`. Before extracting, check it is really that season: its checksum must differ from every other season's file, and the top players and teams should look current. A mislabeled download once turned out to be the 2013 file.
2. `uv run bucco extract player-projections` then `uv run bucco build`.
3. Once a season, after the season ends: `uv run bucco extract mlb-positions` and refit the position-switch matrix with `uv run python scripts/fit_position_switch.py <folder of Savant OAA CSVs>` (download steps are in the script's docstring).
4. `uv run bucco forecast --model steamer_optimized` (saves the forecast; the outlook reads it).
5. `uv run bucco outlook --team PIT`.

## Review before handing over (judgment)

Read the generated page and check these. Report anything odd to the user; do not paper over it in the wording.

- **Off-position free agents** (marked `*`): the optimizer would play them mostly at a position they did not play last season. Moves up the defensive spectrum (outfield to the infield, anywhere to CF or SS) are rare in real baseball and should be rare here; if one appears, mention it.
- **Free agents who have since signed:** the list is the projection file's unsigned players. If the download is old, say so.
- **Replacement level in the lineup:** a large share of a position (more than about 200 PA) going to replacement level means the team's projected roster is thin there, or the fatigue curve is too steep for it. Check before presenting it as a finding.
- **The headline** is picked by rule from the pitching and batting ranks; make sure it matches the story the numbers tell.
- **Compared with the previous outlook:** if one exists, note the biggest changes (wins, ranks, free-agent order) and whether they come from new projections, a new model setting or roster moves.

## Changing the page

- **Wording** (headings, sentences, caveats, labels): edit only `config/outlook_text.yml`. Keep each entry's `{placeholders}` (listed in the comment above it) and keep sentences true for any value. The build fails with the entry name if a placeholder is wrong. Then rebuild with the same options so the same file is overwritten.
- **Numbers, sections, tables, charts:** these are code (`outlook_data.py`, `outlook_render.py`). Make the change, add or update a test in `tests/test_outlook.py`, run `uv run pytest -q tests/test_outlook.py` and `uv run ruff check src tests`, then rebuild.
- **Model settings** (fatigue, position-switch penalties) live in `src/bucco/models/lineup_optimizer.py` and change the forecast too: rerun `bucco backtest --models steamer_optimized` and `bucco forecast --model steamer_optimized`, and record what changed in `docs/R&D/lineup_optimizer.md`.

## Sharing

If the user wants a shareable page, publish the generated file as an artifact (update the existing outlook artifact rather than creating a new one when there is one). Commit only when asked.
