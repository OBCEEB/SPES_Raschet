"""
Baseline models M0 / M1 for horizontal irradiance.

M0: G_hat = B_ref
M1: G_hat = c_month(m) * B_ref  with c_month fit on train years only
    c_month = sum(G_obs) / sum(B_ref) over daytime valid train samples in month m
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


def daytime_valid_mask(
    df: pd.DataFrame,
    obs_col: str = "radiation_wm2",
    bref_col: str = "B_ref",
    require_bref_positive: bool = True,
) -> pd.Series:
    mask = (
        (df["is_daytime"] == 1)
        & df[obs_col].notna()
        & (df.get("qc_negative_q", 0) == 0)
        & df[bref_col].notna()
    )
    if require_bref_positive:
        mask = mask & (df[bref_col] > 0)
    return mask


def fit_m1_monthly_scales(
    df: pd.DataFrame,
    train_years: Sequence[int],
    obs_col: str = "radiation_wm2",
    bref_col: str = "B_ref",
) -> Dict[int, float]:
    """Return c_month for months 1..12; missing months default to 1.0."""
    tmp = df.copy()
    tmp["year"] = pd.DatetimeIndex(tmp["obs_time"]).year
    tmp["month"] = pd.DatetimeIndex(tmp["obs_time"]).month
    mask = daytime_valid_mask(tmp, obs_col=obs_col, bref_col=bref_col)
    mask = mask & tmp["year"].isin(list(train_years))
    scales: Dict[int, float] = {m: 1.0 for m in range(1, 13)}
    if not mask.any():
        return scales
    sub = tmp.loc[mask]
    grouped = sub.groupby("month").agg(sum_obs=(obs_col, "sum"), sum_ref=(bref_col, "sum"))
    for month, row in grouped.iterrows():
        if row["sum_ref"] > 0:
            scales[int(month)] = float(row["sum_obs"] / row["sum_ref"])
    return scales


def apply_models(
    df: pd.DataFrame,
    c_month: Dict[int, float],
    obs_col: str = "radiation_wm2",
    bref_col: str = "B_ref",
) -> pd.DataFrame:
    out = df.copy()
    months = pd.DatetimeIndex(out["obs_time"]).month
    out["G_hat_M0"] = out[bref_col].astype(float)
    out["c_month"] = np.array([float(c_month.get(int(m), 1.0)) for m in months], dtype=float)
    out["G_hat_M1"] = out["c_month"] * out[bref_col].astype(float)
    # Night: set predictions to 0 when not daytime
    night = out["is_daytime"] != 1
    out.loc[night, "G_hat_M0"] = 0.0
    out.loc[night, "G_hat_M1"] = 0.0
    return out


def assign_split(
    times: pd.Series,
    train_years: Sequence[int] = (2023,),
    val_years: Sequence[int] = (2024,),
    test_years: Sequence[int] = (2025,),
) -> pd.Series:
    years = pd.DatetimeIndex(times).year
    out = pd.Series("other", index=times.index if hasattr(times, "index") else range(len(times)))
    out = out.copy()
    # rebuild with proper index
    idx = getattr(times, "index", pd.RangeIndex(len(years)))
    labels = np.array(["other"] * len(years), dtype=object)
    labels[np.isin(years, list(train_years))] = "train"
    labels[np.isin(years, list(val_years))] = "val"
    labels[np.isin(years, list(test_years))] = "test"
    return pd.Series(labels, index=idx)


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    err = y_pred - y_true
    n = len(y_true)
    if n == 0:
        return {
            "n": 0,
            "MAE": float("nan"),
            "RMSE": float("nan"),
            "MBE": float("nan"),
            "nRMSE": float("nan"),
            "mean_obs": float("nan"),
        }
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    mbe = float(np.mean(err))
    mean_obs = float(np.mean(y_true))
    nrmse = float(rmse / mean_obs) if mean_obs > 0 else float("nan")
    return {
        "n": int(n),
        "MAE": mae,
        "RMSE": rmse,
        "MBE": mbe,
        "nRMSE": nrmse,
        "mean_obs": mean_obs,
    }


def metrics_by_split(
    df: pd.DataFrame,
    model_col: str,
    obs_col: str = "radiation_wm2",
    splits: Sequence[str] = ("train", "val", "test"),
) -> pd.DataFrame:
    rows = []
    mask_base = daytime_valid_mask(df, obs_col=obs_col)
    for split in splits:
        m = mask_base & (df["split"] == split)
        mets = regression_metrics(df.loc[m, obs_col].to_numpy(), df.loc[m, model_col].to_numpy())
        mets["split"] = split
        mets["model"] = model_col
        rows.append(mets)
    # overall on val+test or all labelled
    m_all = mask_base & df["split"].isin(list(splits))
    mets = regression_metrics(df.loc[m_all, obs_col].to_numpy(), df.loc[m_all, model_col].to_numpy())
    mets["split"] = "all_splits"
    mets["model"] = model_col
    rows.append(mets)
    return pd.DataFrame(rows)


def energy_sums(
    df: pd.DataFrame,
    value_cols: Sequence[str],
    freq: str,
    obs_col: str = "radiation_wm2",
    interval_hours: float = 0.5,
) -> pd.DataFrame:
    """
    Energy sums in W·h/m² = mean W/m² × interval hours, over daytime slots with valid obs.
    """
    tmp = df.copy()
    tmp["year"] = pd.DatetimeIndex(tmp["obs_time"]).year
    tmp["month"] = pd.DatetimeIndex(tmp["obs_time"]).month
    tmp["date"] = pd.DatetimeIndex(tmp["obs_time"]).date
    mask = (tmp["is_daytime"] == 1) & tmp[obs_col].notna()
    sub = tmp.loc[mask].copy()
    sub[obs_col + "_Wh"] = sub[obs_col].astype(float) * interval_hours
    for col in value_cols:
        sub[col + "_Wh"] = sub[col].astype(float) * interval_hours

    if freq == "daily":
        keys = ["year", "month", "date", "split"]
    elif freq == "monthly":
        keys = ["year", "month", "split"]
    else:
        raise ValueError("freq must be daily or monthly")

    cols_wh = [obs_col + "_Wh"] + [c + "_Wh" for c in value_cols]
    return sub.groupby(keys, as_index=False)[cols_wh].sum()
