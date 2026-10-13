"""
Pipeline stub: export SQLite observations + QC only (no models yet).

Usage (repo root):
  analysis\\.venv\\Scripts\\python.exe analysis/src/run_pipeline.py
  py -3 analysis/src/run_pipeline.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from export_qc import run  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run analysis pipeline (export + QC)")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--stages",
        default="export,qc",
        help="Comma-separated stages. Currently only export+qc are implemented.",
    )
    args = parser.parse_args(argv)
    stages = {s.strip().lower() for s in args.stages.split(",") if s.strip()}
    allowed = {"export", "qc"}
    unknown = stages - allowed
    if unknown:
        print("Unknown stages (ignored for now): {}".format(", ".join(sorted(unknown))))
    if not stages.intersection(allowed) and stages:
        print("No supported stages requested; nothing to do.")
        return 1
    summary = run(args.config)
    print("Pipeline complete (export+qc).")
    print("SQLite rows: {}".format(summary["n_sqlite_rows"]))
    print("Grid rows:   {}".format(summary["n_grid_rows"]))
    print("Present:     {}".format(summary["n_present"]))
    print("Period:      {} -> {}".format(summary["t_min"], summary["t_max"]))
    print("Report:      {}".format(summary["report"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
