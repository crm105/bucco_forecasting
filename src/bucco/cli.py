"""Command-line tool.

    bucco extract mlb-seasons
    bucco extract mlb-standings [--seasons 2024 2025] [--refresh]
    bucco extract projections
    bucco extract all
    bucco build [dbt arguments]      (default: dbt deps, then dbt build)
    bucco backtest [--models constant last_year] [--first-season 2001] [--include-shortened]
    bucco leaderboard [--pirates] [--first-season 2001] [--include-shortened]
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys

import pandas as pd

from bucco.config import DATA_DIR, TRANSFORM_DIR
from bucco.evaluate import backtest, leaderboard
from bucco.extract import mlb_api, projections
from bucco.models import REGISTRY


def _extract(args: argparse.Namespace) -> None:
    if args.target in ("mlb-seasons", "all"):
        mlb_api.extract_seasons()
    if args.target in ("mlb-standings", "all"):
        mlb_api.extract_standings(
            seasons=getattr(args, "seasons", None), refresh=getattr(args, "refresh", False))
    if args.target in ("projections", "all"):
        projections.extract_projections()


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
        frames.append(backtest.run_backtest(REGISTRY[name], team_seasons, features))
    results = pd.concat(frames, ignore_index=True)
    backtest.save_results(results)
    print(leaderboard.leaderboard(backtest.load_results(), args.first_season,
                                    args.include_shortened))


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
    targets.add_parser("projections", help="check and save hand-collected projections")
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
