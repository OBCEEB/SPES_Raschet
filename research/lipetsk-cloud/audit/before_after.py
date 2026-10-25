"""Before/after table for the time-basis fix.

Old: data/lipetsk/csv_v1_time_bug (copy of the pipeline-v1-time-bug outputs) and
the math_audit_numbers.json from git tag pipeline-v1-time-bug.
New: data/lipetsk/csv and audit/math_audit_numbers.json.
Writes reports/time_fix_before_after.json and reports/time_fix_before_after.md.
"""
import csv
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "data" / "lipetsk" / "csv_v1_time_bug"
NEW = ROOT / "data" / "lipetsk" / "csv"
REPORTS = ROOT / "reports"
WINTER = {11, 12, 1, 2, 3}
SUMMER = {5, 6, 7, 8, 9}


def jload(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def old_audit():
    raw = subprocess.run(
        ["git", "show", "pipeline-v1-time-bug:research/lipetsk-cloud/audit/math_audit_numbers.json"],
        cwd=ROOT, capture_output=True, check=True).stdout
    return json.loads(raw.decode("utf-8"))


def rows(path):
    with Path(path).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def kt_means(base):
    d = [r for r in rows(base / "daily_obs_q_only.csv") if r["complete_daylight"] == "1" and r["Kt"]]
    w = [float(r["Kt"]) for r in d if int(r["month"]) in WINTER]
    s = [float(r["Kt"]) for r in d if int(r["month"]) in SUMMER]
    return {"n_complete": len(d), "Kt_winter": round(sum(w) / len(w), 4), "Kt_summer": round(sum(s) / len(s), 4)}


def clim_c(base):
    return {int(r["month"]): float(r["C_vs_sp"]) for r in rows(base / "climatology_q_only.csv")}


def yearwise(base):
    a = jload(base / "actualize_summary.json")["daily_log_Kt"]
    return {y: v["Kt"] for y, v in a["yearwise"].items()}, a.get("yearwise_variants")


def winter_models(base):
    s = jload(base / "winter_models_summary.json")
    return {m: {"Kt_winter_rmse": v["Kt"]["winter"]["rmse"], "Q_winter_rmse": v["Q"]["winter"]["rmse"],
                "Q_winter_mbe": v["Q"]["winter"]["mbe"]} for m, v in s["models"].items()}, s["best_by_winter_Q_rmse"]


def scenarios(a):
    s1, s2, s4 = a["F_S1_measured_GHI"], a["F_S2_oracle_smooth_Q_sum_mjm2"], a["F_S4_baseline_log_smooth_Q_sum_mjm2"]
    out = {}
    for season in ("winter", "other"):
        q1 = s1[season]["Q_sum_mjm2"]
        out[season] = {
            "S1_Q_mjm2": q1, "S2_Q_mjm2": s2[season], "S4_Q_mjm2": s4[season],
            "S2_over_S1": round(s2[season] / q1, 3), "S4_over_S1": round(s4[season] / q1, 3),
            "S1_share_slots_zero_power": s1[season]["share_Q_zero"],
        }
    return out


def main():
    ao, an = old_audit(), jload(ROOT / "audit" / "math_audit_numbers.json")
    yo, _ = yearwise(OLD)
    yn, variants = yearwise(NEW)
    wo, best_o = winter_models(OLD)
    wn, best_n = winter_models(NEW)
    gti_o, gti_n = jload(OLD / "gti_summary.json"), jload(NEW / "gti_summary.json")
    col_o, col_n = jload(OLD / "collector_summary.json"), jload(NEW / "collector_summary.json")
    out = {
        "days": {"old": kt_means(OLD), "new": kt_means(NEW),
                 "log_model_days_old": ao["F_baseline_log"]["recomputed"]["all"]["n"],
                 "log_model_days_new": an["F_baseline_log"]["recomputed"]["all"]["n"]},
        "C_climatology": {"old": clim_c(OLD), "new": clim_c(NEW),
                          "C_year_old": gti_o["C_year"], "C_year_new": gti_n["C_year"]},
        "year_composites": {
            "H_year_mjm2": [gti_o["H_year_eq_mjm2"], gti_n["H_year_eq_mjm2"]],
            "IT_year_mjm2": [gti_o["IT_year_eq_mjm2"], gti_n["IT_year_eq_mjm2"]],
            "Qu_year_mjm2_dT40": [col_o["iso9806_composite_year"]["Qu_mjm2"], col_n["iso9806_composite_year"]["Qu_mjm2"]],
            "Qcs_year_mjm2_dT40": [col_o["iso9806_composite_year"]["Qcs_mjm2"], col_n["iso9806_composite_year"]["Qcs_mjm2"]],
        },
        "log_model_yearwise_Kt": {"old": yo, "new": yn},
        "log_model_winter_Kt": {"old": ao["F_baseline_log"]["stored_winter_Kt"], "new": an["F_baseline_log"]["stored_winter_Kt"]},
        "log_model_variants_new": variants,
        "ngo_9999_sensitivity": {"old": ao["G_ngo_9999_sensitivity"], "new": an["G_ngo_9999_sensitivity"]},
        "scenarios": {"old": scenarios(ao), "new": scenarios(an)},
        "gcrit_slot_specific": {"old": ao["F_gcrit_slot_specific"], "new": an["F_gcrit_slot_specific"]},
        "winter_models": {"old": wo, "new": wn, "best_old": best_o, "best_new": best_n},
    }
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "time_fix_before_after.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("days", "year_composites", "scenarios", "log_model_winter_Kt")}, ensure_ascii=False, indent=1))
    print("C old", out["C_climatology"]["old"])
    print("C new", out["C_climatology"]["new"])
    print("yearwise old", yo)
    print("yearwise new", yn)
    print("winter models old", wo, best_o)
    print("winter models new", wn, best_n)
    print("variants", json.dumps(variants, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main()
