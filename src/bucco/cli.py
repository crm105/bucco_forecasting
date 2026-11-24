"""Command-line tool.

    bucco extract mlb-seasons
    bucco extract mlb-standings [--seasons 2024 2025] [--refresh]
    bucco extract mlb-positions [--seasons 2024 2025] [--refresh]
    bucco extract mlb-schedules [--seasons 2026 2027] [--refresh]
    bucco extract projections
    bucco extract player-projections
    bucco extract all
    bucco build [dbt arguments]      (default: dbt deps, then dbt build)
    bucco backtest [--models constant last_year] [--first-season 2001] [--include-shortened]
    bucco forecast --model last_year [--season 2027] [--as-of 2027-03-01] [--no-save]
    bucco report [--model last_year] [--season 2027] [--as-of 2027-03-15]
    bucco outlook [--team PIT] [--model steamer_optimized] [--season 2027]
    bucco scenario --team PIT [--add "Ian Happ" ...] [--remove "Bryan Reynolds" ...]
    bucco leaderboard [--pirates] [--first-season 2001] [--include-shortened]
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from datetime import date

import pandas as pd

from bucco import forecast
from bucco.config import DATA_DIR, TRANSFORM_DIR
from bucco.evaluate import backtest, leaderboard
from bucco.extract import mlb_api, mlb_positions, player_projections, projections
from bucco.models import REGISTRY
from bucco.report import data as report_data
from bucco.report import outlook_data, outlook_render, render


def _extract(args: argparse.Namespace) -> None:
    if args.target in ("mlb-seasons", "all"):
        mlb_api.extract_seasons()
    if args.target in ("mlb-standings", "all"):
        mlb_api.extract_standings(
            seasons=getattr(args, "seasons", None), refresh=getattr(args, "refresh", False))
    if args.target in ("mlb-schedules", "all"):
        mlb_api.extract_schedules(
            seasons=getattr(args, "seasons", None), refresh=getattr(args, "refresh", False))
    if args.target in ("mlb-positions", "all"):
        mlb_positions.extract_positions(
            seasons=getattr(args, "seasons", None), refresh=getattr(args, "refresh", False))
    if args.target in ("projections", "all"):
        projections.extract_projections()
    if args.target in ("player-projections", "all"):
        player_projections.extract_player_projections()


def _build(args: argparse.Namespace) -> None:
    """Run dbt from the transform folder, pointed at the same data folder as the extracts."""
    env = {**os.environ, "BUCCO_DATA_DIR": str(DATA_DIR), "DBT_PROFILES_DIR": str(TRANSFORM_DIR)}
    commands = [args.dbt_args] if args.dbt_args else [["deps"], ["build"]]
    for command in commands:
        subprocess.run(["dbt", *command], cwd=TRANSFORM_DIR, env=env, check=True)


def _backtest(args: argparse.Namespace) -> None:
    """Run each model through the walk-forward backtest, save results, show the leaderboard."""
    unknown = set(args.models or []) - set(REGISTRY)
    if unknown:
        raise ValueError(f"unknown models {sorted(unknown)}; choose from {sorted(REGISTRY)}")
    team_seasons, features = backtest.load_inputs()
    frames = []
    for name in args.models or REGISTRY:
        logging.getLogger(__name__).info("Backtesting %s", name)
        frames.append(backtest.run_backtest(REGISTRY[name], team_seasons, features,
                                            seasons=backtest.supported_seasons(REGISTRY[name],
                                                                               team_seasons)))
    results = pd.concat(frames, ignore_index=True)
    backtest.save_results(results)
    print(leaderboard.leaderboard(backtest.load_results(), args.first_season,
                                    args.include_shortened))


def _forecast(args: argparse.Namespace) -> None:
    """Fit one model on all completed seasons and forecast the upcoming one."""
    if args.model not in REGISTRY:
        raise ValueError(f"unknown model {args.model!r}; choose from {sorted(REGISTRY)}")
    team_seasons, features = backtest.load_inputs()
    result = forecast.make_forecast(REGISTRY[args.model], team_seasons, features,
                                    season=args.season, as_of=args.as_of)
    if not args.no_save:
        forecast.save_forecast(result)
    print(forecast.format_forecast(result))


def _report(args: argparse.Namespace) -> None:
    """Write an HTML report from saved forecasts and backtest results."""
    if args.model and args.model not in REGISTRY:
        raise ValueError(f"unknown model {args.model!r}; choose from {sorted(REGISTRY)}")
    data = report_data.build_report_data(args.model, args.season, args.as_of)
    print(f"Wrote {render.write_report(data)}")


def _outlook(args: argparse.Namespace) -> None:
    """Write a team outlook page from the saved forecast and the player projections."""
    data = outlook_data.build_outlook_data(args.team.upper(), args.season, args.model,
                                           args.as_of)
    print(f"Wrote {outlook_render.write_outlook(data)}")


def _scenario(args: argparse.Namespace) -> None:
    """Re-optimize a team's lineup with players added or removed and show what changes."""
    from bucco.models.scenario import ScenarioError, ScenarioLab

    if not args.add and not args.remove:
        sys.exit("give at least one --add or --remove")
    try:
        lab = ScenarioLab(args.season, args.source)
        print(lab.run(args.team, add=args.add or (), remove=args.remove or ()).report())
    except ScenarioError as e:
        sys.exit(str(e))


def _leaderboard(args: argparse.Namespace) -> None:
    results = backtest.load_results()
    print(leaderboard.leaderboard(results, args.first_season, args.include_shortened))
    if args.pirates:
        print("\nPirates error by season (wins, predicted minus actual):")
        print(leaderboard.pirates_view(results))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="bucco", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    extract = commands.add_parser("extract", help="download or read raw data")
    targets = extract.add_subparsers(dest="target", required=True)
    targets.add_parser("mlb-seasons", help="season calendar")
    standings = targets.add_parser("mlb-standings", help="final standings, one file per season")
    standings.add_argument("--seasons", type=int, nargs="*", help="only these seasons")
    standings.add_argument("--refresh", action="store_true", help="fetch again even if saved")
    schedules = targets.add_parser("mlb-schedules",
                                   help="regular-season schedules, one file per season")
    schedules.add_argument("--seasons", type=int, nargs="*", help="only these seasons")
    schedules.add_argument("--refresh", action="store_true", help="fetch again even if saved")
    positions = targets.add_parser("mlb-positions",
                                   help="who played where, one file per season (30 requests each)")
    positions.add_argument("--seasons", type=int, nargs="*", help="only these seasons")
    positions.add_argument("--refresh", action="store_true", help="fetch again even if saved")
    targets.add_parser("projections", help="check and save hand-collected projections")
    targets.add_parser("player-projections",
                       help="check and save hand-downloaded player projections (ZiPS etc.)")
    targets.add_parser("all", help="all of the above")
    extract.set_defaults(func=_extract)

    build = commands.add_parser("build", help="run dbt (models, seeds and tests)")
    build.add_argument("dbt_args", nargs=argparse.REMAINDER, help="passed to dbt as given")
    build.set_defaults(func=_build)

    bt = commands.add_parser("backtest", help="score models on every past season")
    bt.add_argument("--models", nargs="*", help=f"default: all of {sorted(REGISTRY)}")
    bt.add_argument("--first-season", type=int, help="only score seasons from this year on")
    bt.add_argument("--include-shortened", action="store_true",
                    help="score the 60-game 2020 season too (left out by default)")
    bt.set_defaults(func=_backtest)

    fc = commands.add_parser("forecast", help="forecast the upcoming season with a model")
    fc.add_argument("--model", required=True, help=f"one of {sorted(REGISTRY)}")
    fc.add_argument("--season", type=int, help="default: the season after the latest complete one")
    fc.add_argument("--as-of", type=date.fromisoformat, metavar="YYYY-MM-DD",
                    help="forecast date to record (default: today)")
    fc.add_argument("--no-save", action="store_true", help="print only; do not store")
    fc.set_defaults(func=_forecast)

    rep = commands.add_parser("report", help="write an HTML forecast report")
    rep.add_argument("--model", help="default: the best model on the leaderboard")
    rep.add_argument("--season", type=int, help="default: the upcoming season")
    rep.add_argument("--as-of", metavar="YYYY-MM-DD",
                     help="use the saved forecast with this as-of date (default: latest)")
    rep.set_defaults(func=_report)

    out = commands.add_parser("outlook", help="write a team outlook page (positions, free agents)")
    out.add_argument("--team", default="PIT", help="team abbreviation (default: PIT)")
    out.add_argument("--model", default="steamer_optimized",
                     help="a player-projection model (default: steamer_optimized)")
    out.add_argument("--season", type=int, help="default: the latest season with a forecast")
    out.add_argument("--as-of", metavar="YYYY-MM-DD",
                     help="use the saved forecast with this as-of date (default: latest)")
    out.set_defaults(func=_outlook)

    scen = commands.add_parser("scenario",
                               help="re-optimize a team's lineup with players added or removed")
    scen.add_argument("--team", default="PIT", help="team abbreviation (default: PIT)")
    scen.add_argument("--add", action="append", metavar="PLAYER",
                      help="a free agent or another team's player, by name or MLBAM id "
                           "(repeat for several)")
    scen.add_argument("--remove", action="append", metavar="PLAYER",
                      help="one of the team's own players (repeat for several)")
    scen.add_argument("--source", default="steamer", help="projection source (default: steamer)")
    scen.add_argument("--season", type=int, help="default: the latest projected season")
    scen.set_defaults(func=_scenario)

    board = commands.add_parser("leaderboard", help="show saved backtest results")
    board.add_argument("--pirates", action="store_true", help="also show Pirates errors")
    board.add_argument("--first-season", type=int, help="only score seasons from this year on")
    board.add_argument("--include-shortened", action="store_true",
                    help="score the 60-game 2020 season too (left out by default)")
    board.set_defaults(func=_leaderboard)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        args.func(args)
    except (subprocess.CalledProcessError, ValueError, RuntimeError) as error:
        sys.exit(f"error: {error}")


if __name__ == "__main__":
    main()
