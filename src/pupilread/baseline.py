"""Stage 3.3, baseline correction: reader means, the baseline itself and the low-baseline check."""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd

from ._utils import TRIAL_KEY, check_columns, copy_attrs, ok_mask, warn_order


def reader_means(bins: pd.DataFrame, column: str = "pupil") -> pd.Series:
    """Mean pupil size of each reader over all valid samples (bins weighted by their valid samples).

    This is the denominator of the paper's scaling: changes are expressed as a percentage of the reader mean, so that
    readers and eyes with different pupil-size units become comparable (Section 3.3).
    """
    check_columns(bins, ["reader", column, "n_valid"], "reader_means")
    v = bins[column].to_numpy(float)
    w = bins["n_valid"].to_numpy(float)
    m = np.isfinite(v) & (w > 0)
    d = pd.DataFrame({"reader": bins["reader"].to_numpy()[m], "vw": v[m] * w[m], "w": w[m]})
    g = d.groupby("reader", sort=False)
    out = g["vw"].sum() / g["w"].sum()
    out.name = "reader_mean"
    return out


def _input_column(bins: pd.DataFrame, column: Optional[str]) -> str:
    if column is not None:
        if column == "pupil" and "pupil_corrected" in bins.columns:
            warn_order("baseline(): a gaze-corrected trace (pupil_corrected) exists but the baseline is computed on the "
                       "uncorrected pupil; pass column='pupil_corrected' or drop the corrected column")
        return column
    return "pupil_corrected" if "pupil_corrected" in bins.columns else "pupil"


def baseline(bins: pd.DataFrame, window: Tuple[float, float] = (0, 200), method: str = "subtractive",
             scale: Optional[str] = "reader_mean", column: Optional[str] = None, min_valid: Optional[float] = None,
             means: Optional[pd.Series] = None) -> pd.DataFrame:
    """Baseline correction (stage 3.3; Python 2 of the paper).

    Parameters
    ----------
    bins : DataFrame
        Binned trace (:func:`bin`), gaze-corrected first if a correction is used (:func:`correct_gaze`).
    window : (start, end)
        Baseline window in ms from text onset (paper: 0 to 200 ms, which ends before the light reflex to the text).
    method : {"subtractive", "divisive", "none"}
        ``subtractive``: pupil minus baseline (paper). ``divisive``: change as a percentage of the trial's baseline.
        ``none``: no baseline correction; pupil minus the reader mean.
    scale : {"reader_mean", "baseline_mean", None}
        Denominator of subtractive changes: the reader's mean pupil size (paper), the reader's mean baseline, or none
        (raw units).
    column : str, optional
        Trace to correct; by default ``pupil_corrected`` if :func:`correct_gaze` was applied, else ``pupil``.
    min_valid : float, optional
        Share of valid samples a bin needs (default: the ``ok`` column of :func:`bin`).
    means : Series, optional
        Reader means to use (default: :func:`reader_means` of the uncorrected pupil).

    Returns
    -------
    DataFrame
        The bins with ``change`` (per bin), ``baseline`` (per trial, raw units) and ``baseline_pct`` (the baseline as a
        percentage of the reader mean; :func:`low_baselines` flags implausibly small ones).
    """
    if method not in ("subtractive", "divisive", "none"):
        raise ValueError("baseline: method must be 'subtractive', 'divisive' or 'none'")
    if scale not in ("reader_mean", "baseline_mean", None):
        raise ValueError("baseline: scale must be 'reader_mean', 'baseline_mean' or None")
    col = _input_column(bins, column)
    check_columns(bins, ["reader", "trial", "time", col], "baseline")
    out = bins.drop(columns=[c for c in ("change", "baseline", "baseline_pct") if c in bins.columns]).copy()
    ok = ok_mask(out, min_valid)
    rm = means if means is not None else reader_means(out)
    rmv = out["reader"].map(rm).to_numpy(float)
    t = out["time"].to_numpy(float)
    a, b = window
    inb = ok & (t >= a) & (t < b)
    v = out[col].to_numpy(float)
    bt = pd.DataFrame({"reader": out["reader"].to_numpy()[inb], "trial": out["trial"].to_numpy()[inb], "v": v[inb]})
    bs = bt.groupby(TRIAL_KEY, sort=False)["v"].mean().rename("baseline").reset_index()
    out = out.merge(bs, on=TRIAL_KEY, how="left")
    base = out["baseline"].to_numpy(float)
    rmv = out["reader"].map(rm).to_numpy(float)
    if method == "none":
        change = 100 * (out[col].to_numpy(float) - rmv) / rmv
    elif method == "divisive":
        change = 100 * (out[col].to_numpy(float) - base) / base
    else:
        if scale == "reader_mean":
            den = rmv
        elif scale == "baseline_mean":
            rb = bs.groupby("reader")["baseline"].mean()
            den = out["reader"].map(rb).to_numpy(float)
        else:
            den = 1.0
        mult = 100.0 if scale is not None else 1.0
        change = mult * (out[col].to_numpy(float) - base) / den
    out["change"] = np.where(ok, change, np.nan)
    out["baseline_pct"] = 100 * base / rmv
    return copy_attrs(bins, out, baseline=dict(window=tuple(window), method=method, scale=scale, column=col))


def low_baselines(data: pd.DataFrame, min_pct: float = 60) -> pd.DataFrame:
    """Flag trials whose baseline is implausibly small (stage 3.3; paper: below 60% of the reader mean).

    Small baselines come from blinks and other distortions in the baseline window and inflate the corrected values.
    The cut-off is best read from a histogram of baselines with log-scaled counts (:func:`plot_baselines`).

    Returns
    -------
    DataFrame
        One row per trial with ``baseline_pct`` and ``low`` (True below ``min_pct``); trials without a baseline are
        listed with ``low`` = True and ``reason`` = "no baseline".
    """
    check_columns(data, ["reader", "trial", "baseline_pct"], "low_baselines (run baseline first)")
    cols = [c for c in ("reader", "item", "trial", "version", "eye", "baseline_pct") if c in data.columns]
    T = data.drop_duplicates(TRIAL_KEY)[cols].reset_index(drop=True)
    T["low"] = ~(T["baseline_pct"] >= min_pct)
    T["reason"] = np.where(T["baseline_pct"].isna(), "no baseline", np.where(T["low"], f"below {min_pct:g}%", ""))
    T.attrs = {"min_pct": min_pct}
    return T
