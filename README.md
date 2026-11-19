# Replication package: How Python projects pin their pre-commit hooks

Data and scripts for the study of `.pre-commit-config.yaml` files in the 5,000 most downloaded PyPI projects
(snapshot of 19 November 2026).

## Contents
- `data/` - the frame and everything derived from it:
  `top_dump.json` (top-pypi-packages listing used), `pypi_repos.json` (project -> GitHub repository),
  `heads.json` (repository -> commit read), `files_index.json` (path -> HTTP status at that commit),
  `parsed.json` (every configuration entry), `hook_tags.json` (tags of every hook repository),
  `hook_redirects.json` and `former_owners.json` (renamed hook repositories), `tool_releases.json` and
  `mirrors.json` (PyPI release dates of hooks that mirror a PyPI project).
- `research/hook_categories.csv` - the hand-made category of every hook repository used by 3 or more
  configurations.
- `results/` - `numbers.json` (every number in the paper), `entries.csv` (one row per pinned entry),
  `rq1_hook_repositories.csv`, `rq4_drift.csv`, and the integrity-check logs.
- `scripts/` - collection (`01`), parsing and tag resolution (`02`), analysis (`03`), integrity check (`04`),
  tables (`06`).

## Reproducing
Python 3.11+ with `pyyaml` and `packaging`, and `git` on the path. The configuration files themselves belong to
the projects that publish them and are not redistributed. `python scripts/01_collect.py` re-fetches each of them
from the commit recorded in `data/heads.json` (existing entries are reused, so nothing is re-resolved), then run
`02`, `03` and `04`. All network access is unauthenticated.

## Licence
Data and documentation: CC BY 4.0. Code: MIT.
