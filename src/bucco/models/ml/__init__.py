"""Learned player models (gradient-boosted trees) on top of Marcel.

* `core`: walk-forward fitting with per-season tuning, lagged history, Opening Day status, scores.
* `pitchers`: pitcher innings and FIP-based rates (`marcel_ml_pitchers`).
* `hitters`: hitter plate appearances, used as given (`marcel_ml_hitter_pa`).

`bucco fit-ml` fits them and saves each one's predictions; the registered models read those.
"""

TARGETS = ("pitchers", "hitters")
