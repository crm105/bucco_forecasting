# Working conventions for coding agents

## Git

- **Commit on a feature branch, never directly on `main`.** Start each piece of work on its own
  branch off `main`, named for the work (for example `own-player-projections`,
  `pitcher-components`). Do not use a `feature/` prefix: a branch named `feature` already
  exists, so git cannot create `feature/<name>`.
- **Small, atomic commits.** Group changes by logical step (for example: extract, dbt models,
  models, report), each leaving the tests passing. Write a short subject line and a body that
  says what changed and why, with results where relevant (backtest RMSE).
- **No AI attribution** in commit messages or pull requests: no `Co-Authored-By` trailer and no
  "Generated with" line.
- Push the branch with `git push -u origin <branch>`. Open a pull request or merge into `main`
  only when asked.
- Leave unrelated uncommitted work alone; mention it instead of committing it.

## Before committing

- `uv run pytest -q` and `uv run ruff check src tests` pass.
- After dbt changes, `uv run bucco build` passes.
- Generated reports under `reports/` are rebuilt from code (`bucco outlook`, `bucco report`),
  never edited by hand.
