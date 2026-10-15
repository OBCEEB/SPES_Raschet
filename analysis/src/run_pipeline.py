"""
Analysis pipeline: export+QC, then clear-sky / B_ref / M0–M1.

Usage (repo root):
  analysis\\.venv\\Scripts\\python.exe analysis/src/run_pipeline.py
  analysis\\.venv\\Scripts\\python.exe analysis/src/run_pipeline.py --stages export,qc,models
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from export_qc import run as run_export_qc  # noqa: E402
from run_models import run as run_models  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run analysis pipeline")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--stages",
        default="export,qc,models",
        help="Comma-separated stages: export, qc, models",
    )
    args = parser.parse_args(argv)
    stages = {s.strip().lower() for s in args.stages.split(",") if s.strip()}
    allowed = {"export", "qc", "models"}
    unknown = stages - allowed
    if unknown:
        print("Unknown stages (ignored): {}".format(", ".join(sorted(unknown))))
    if not stages.intersection(allowed):
        print("No supported stages requested; nothing to do.")
        return 1

    if stages.intersection({"export", "qc"}):
        summary = run_export_qc(args.config)
        print("Export+QC complete.")
        print("SQLite rows: {}".format(summary["n_sqlite_rows"]))
        print("Grid rows:   {}".format(summary["n_grid_rows"]))
        print("Present:     {}".format(summary["n_present"]))
        print("Report:      {}".format(summary["report"]))

    if "models" in stages:
        msum = run_models(args.config)
        print("Models M0/M1 complete.")
        print("Report:      {}".format(msum["report"]))
        print("Rows:        {}".format(msum["n_rows"]))

    print("Pipeline done. Stages: {}".format(", ".join(sorted(stages & allowed))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
