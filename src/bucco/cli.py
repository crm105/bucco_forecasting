"""Command-line tool.

    bucco extract mlb-seasons
    bucco extract mlb-standings [--seasons 2024 2025] [--refresh]
    bucco extract projections
    bucco extract all
    bucco build [dbt arguments]      (default: dbt deps, then dbt build)
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys

from bucco.config import DATA_DIR, TRANSFORM_DIR
from bucco.extract import mlb_api, projections


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

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        args.func(args)
    except (subprocess.CalledProcessError, ValueError, RuntimeError) as error:
        sys.exit(f"error: {error}")


if __name__ == "__main__":
    main()
