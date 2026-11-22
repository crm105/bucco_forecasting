---
name: update-report-text
description: Apply a forecaster's feedback to the written content of the Bucco Forecasting HTML report (headings, explanations, captions, caveats, labels, footer) and rebuild the report. Use when the user shares feedback, comments or edit requests about the wording or descriptions in a generated report under reports/.
---

# Update report text from feedback

The report's written content lives in **`config/report_text.yml`**. The HTML files in `reports/` are generated from it by `bucco report` and are overwritten on every build. Never edit a generated HTML file: the change would be lost, and the next report would not have it.

## Workflow

1. **Collect the feedback.** Get it from the user's message or the file they point to. If the report it refers to is unclear, use the newest file in `reports/<season>/`.
2. **Read** `config/report_text.yml` in full. The comment above each entry lists the `{placeholders}` it may use.
3. **Map each piece of feedback to an entry.** Match the quoted wording against the YAML values, and against the generated HTML if the feedback quotes the page. If the text is not in the YAML, it is data or layout rather than prose (see "Out of scope").
4. **Edit only the YAML values.** Keep the keys, structure and placeholders. Keep the wording true for any number the placeholder could take.
5. **Rebuild** with the same options as the report being revised so the same file is overwritten:
   ```
   uv run bucco report --model <model> --season <season> --as-of <as-of>
   ```
   The model, season and as-of date are in the report's file name: `reports/<season>/<model>_<as-of>.html`. With no options it rebuilds the newest forecast.
6. **Verify.** The build validates the YAML and fails with the entry name if a placeholder is wrong or an entry is missing. Then check the new HTML contains the new wording and no longer contains the old. Run `uv run --extra dev pytest tests/test_report.py -q` if you changed anything besides wording.
7. **Report back**: list each feedback item, the entry changed (old wording to new), and anything not changed and why. Do not commit unless asked.

## Rules for wording

- Plain text. `**bold**` becomes bold. Anything else is shown as typed.
- Keep every `{placeholder}` the entry already uses, unless the feedback asks to drop that number. Only the placeholders in the comment above an entry are allowed.
- Do not state anything the numbers could contradict. Examples: do not write "a small chance" beside a probability, or "the Pirates are expected to improve" beside a changing wins figure.
- Keep these facts accurate and present: the 2020 (60-game) season is excluded from the scores; the model is a simple baseline; the data source is the MLB Stats API and personal, non-commercial use; the forecast does not know about events after the as-of date.
- Do not add claims about how a model works that the code does not do. The current models use only team records.
- A new model needs an entry under `model_labels`.

## Out of scope: say so instead of editing

Tell the user, and offer to do it as a separate code change, when feedback asks for:

- different numbers, ranges, probabilities or chart data (these come from the saved forecast and backtest, not the text file),
- new sections, charts, tables, colours or layout (`src/bucco/report/render.py`, `charts.py`),
- playoff or division odds (needs the season simulator, which does not exist yet),
- changes to what the badge says about forecast of record logic (`src/bucco/report/data.py`).

If feedback disagrees with a number, do not reword the text to hide it. Pass it to the user as a possible model or data question.

## Ambiguous feedback

If feedback has two reasonable readings that would change the meaning, ask the user. For plain style edits, make the change and show the result.
