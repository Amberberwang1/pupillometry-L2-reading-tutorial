"""Stage 3.7, control predictors: trial means adjusted for factors that covary with pupil size during reading.

Following Mathot et al. (2015), factors such as time, gaze position and eccentricity, local text density (a proxy for
local luminance), fixation duration and the distance to the next fixation can be partialled out. Their slopes are
estimated within trials, on bins centred on their trial means, so that the contrast between versions, which lies between
trials, cannot enter them; each trial mean is then adjusted by the slopes times the trial's deviation from the grand
mean of each covariate.
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ._utils import TRIAL_KEY, check_columns, ok_mask
from .gaze import foreshortening
from .levels import retained_fixations


def add_covariates(bins: pd.DataFrame, fixations: Optional[pd.DataFrame] = None, center: Tuple[float, float] = (512, 384),
                   px_per_degree: Optional[float] = None, time_center_s: float = 10.0, min_fix_ms: float = 80,
                   layout=None) -> pd.DataFrame:
    """Add generic control predictors to the bins.

    Adds ``time_s`` (s from text onset), ``time2`` ((time_s - time_center_s) squared), ``eccentricity`` (distance of
    gaze from ``center``, pixels) and, if ``fixations`` are given, ``fix_duration`` (duration of the fixation in
    progress, i.e. the last retained fixation that started at or before the bin) and ``next_distance`` (distance to the
    next fixation, in degrees if ``px_per_degree`` is given, else pixels). With a measured ``layout``
    (:func:`read_layout`), also ``cos_theta``: the cosine of the angle between the lines from the recorded eye to the
    camera lens and to the gaze position (:func:`foreshortening`; missing where gaze is missing). Study-specific
    predictors, such as local text density computed from interest areas, can be added as further columns.
    """
    out = bins.copy()
    out["time_s"] = out["time"].to_numpy(float) / 1000.0
    out["time2"] = (out["time_s"] - time_center_s) ** 2
    out["eccentricity"] = np.hypot(out["gaze_x"] - center[0], out["gaze_y"] - center[1])
    if layout is not None:
        check_columns(out, ["eye"], "add_covariates")
        out["cos_theta"] = foreshortening(out, layout)
    if fixations is not None:
        F = retained_fixations(fixations, min_fix_ms).sort_values(TRIAL_KEY + ["start"], kind="mergesort").copy()
        g = F.groupby(TRIAL_KEY, sort=False)
        nx, ny = g["x"].shift(-1), g["y"].shift(-1)
        dist = np.hypot(nx - F["x"], ny - F["y"])
        F["next_distance"] = dist / px_per_degree if px_per_degree else dist
        F["fix_duration"] = F["duration"].astype(float)
        F2 = F[TRIAL_KEY + ["start", "fix_duration", "next_distance"]].rename(columns={"start": "_t"})
        F2["_t"] = F2["_t"].astype(float)
        F2 = F2.sort_values("_t", kind="mergesort")
        o = out.assign(_t=out["time"].astype(float), _row=np.arange(len(out))).sort_values("_t", kind="mergesort")
        for c in TRIAL_KEY:
            o[c] = o[c].astype(str)
            F2[c] = F2[c].astype(str)
        m = pd.merge_asof(o, F2, on="_t", by=TRIAL_KEY, direction="backward").sort_values("_row")
        out["fix_duration"] = m["fix_duration"].to_numpy()
        out["next_distance"] = m["next_distance"].to_numpy()
    out.attrs = dict(bins.attrs or {})
    return out


def control_predictors(bins: pd.DataFrame, covariates: Sequence[str], window: Tuple[float, float] = (500, 20000),
                       min_baseline_pct: Optional[float] = 60, column: str = "change", name: str = "change_adjusted",
                       complete_cases: Optional[Sequence[str]] = None):
    """Trial means adjusted for control predictors estimated within trials (Section 3.7).

    Parameters
    ----------
    bins : DataFrame
        Bins after :func:`baseline` with the covariate columns (see :func:`add_covariates`).
    covariates : list of str
        Columns to partial out. Bins with a missing value in any of them are left out, so the unadjusted mean on the
        same bins is returned too.
    window : (start, end)
        Window in ms from text onset.
    min_baseline_pct : float or None
        Analysed trials only (baseline at least this % of the reader mean), as in the paper.
    complete_cases : list of str, optional
        Columns that must be present for a bin to be used (default: ``covariates`` and gaze position). Pass the
        largest covariate set to compare nested adjustments on the same bins, as in the paper.

    Returns
    -------
    (DataFrame, Series)
        One row per trial with the unadjusted mean on the bins used (``change_same_bins``) and the adjusted mean
        (``name``); and the within-trial slopes.
    """
    req = list(dict.fromkeys(list(complete_cases or covariates) + [c for c in ("gaze_x", "gaze_y") if c in bins.columns]))
    need = list(dict.fromkeys(list(covariates) + req + [column, "baseline_pct"]))
    check_columns(bins, need, "control_predictors")
    ok = ok_mask(bins)
    t = bins["time"].to_numpy(float)
    m = ok & (t >= window[0]) & (t < window[1])
    if min_baseline_pct is not None:
        m &= bins["baseline_pct"].to_numpy(float) >= min_baseline_pct
    W = bins.loc[m, TRIAL_KEY + need].dropna(subset=list(dict.fromkeys(req + list(covariates) + [column])))
    g = W.groupby(TRIAL_KEY, sort=False)
    cols = [column] + list(covariates)
    dm = W[cols] - g[cols].transform("mean")
    X = dm[list(covariates)].to_numpy(float)
    b, *_ = np.linalg.lstsq(X, dm[column].to_numpy(float), rcond=None)
    TM = g[cols].mean().reset_index()
    GM = TM[list(covariates)].mean()
    adj = TM[column] - ((TM[list(covariates)] - GM) * b).sum(axis=1)
    info = [c for c in ("reader", "item", "trial", "version", "eye", "baseline_pct") if c in bins.columns]
    out = bins.drop_duplicates(TRIAL_KEY)[info].merge(TM[TRIAL_KEY + [column]].rename(columns={column: "change_same_bins"}),
                                                     on=TRIAL_KEY, how="inner")
    out = out.merge(pd.DataFrame({"reader": TM["reader"], "trial": TM["trial"], name: adj}), on=TRIAL_KEY, how="left")
    return out, pd.Series(b, index=list(covariates), name="slope")
