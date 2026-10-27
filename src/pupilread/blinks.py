"""Stage 3.2, blinks and artifacts: padding, pupil-based detection, interpolation, data loss and trial exclusion."""
from __future__ import annotations

from collections import namedtuple
from typing import Iterable, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from scipy.interpolate import CubicSpline

from ._utils import (TRIAL_KEY, check_columns, copy_attrs, dilate, ms_to_samples, onsets, runs, sampling_rate,
                     sort_trials, trial_slices)


def pad_blinks(samples: pd.DataFrame, pad_ms: float = 100, pupil_range: Tuple[float, float] = (100, 10000)) -> pd.DataFrame:
    """Pad every blink and set padded and invalid samples to missing (stage 3.2; Python 2 of the paper).

    Parameters
    ----------
    samples : DataFrame
        Sample table (:func:`read_eyelink`, :func:`read_csv`).
    pad_ms : float
        Padding on each side of every blink, in ms (paper: 100 ms; 50 to 100 ms are common).
    pupil_range : (low, high)
        Pupil values outside this range, like missing values, count as invalid (paper: 100 to 10,000 area units).

    Returns
    -------
    DataFrame
        The samples with ``pupil`` set to NaN where invalid or within a padded blink, and new columns ``pupil_raw``
        (as recorded), ``invalid``, ``blink_pad`` (padded blink, blink included) and ``valid``.
    """
    check_columns(samples, ["reader", "trial", "time", "pupil", "in_blink"], "pad_blinks")
    s = sort_trials(samples)
    hz = sampling_rate(s)
    k = ms_to_samples(pad_ms, hz)
    raw = s["pupil_raw"].to_numpy(float) if "pupil_raw" in s.columns else s["pupil"].to_numpy(float)
    lo, hi = pupil_range
    invalid = ~np.isfinite(raw) | (raw < lo) | (raw > hi)
    blink = s["in_blink"].to_numpy(bool)
    pad = np.zeros(len(s), bool)
    for a, b in trial_slices(s):
        pad[a:b] = dilate(blink[a:b], k)
    valid = ~invalid & ~pad
    out = s.copy()
    out["pupil_raw"] = raw
    out["pupil"] = np.where(valid, raw, np.nan)
    out["invalid"] = invalid
    out["blink_pad"] = pad
    out["valid"] = valid
    return copy_attrs(s, out, pad_ms=pad_ms, pupil_range=tuple(pupil_range), hz=hz)


def detect_blinks(samples: pd.DataFrame, method: str = "speed", mad_k: float = 16, pad_ms: float = 50,
                  smooth_ms: float = 10, pupil_range: Tuple[float, float] = (100, 10000),
                  column: str = "in_blink") -> pd.DataFrame:
    """Flag blinks and artifacts from the pupil signal, for trackers without blink events (Kret & Sjak-Shie, 2019).

    Samples count as artifacts if pupil size is missing or outside ``pupil_range``, or if dilation speed exceeds the
    trial's median speed plus ``mad_k`` median absolute deviations; speed outliers are widened by ``pad_ms``. Speed is
    computed on ``smooth_ms`` means, because at 1,000 Hz the quantised pupil signal makes the median speed zero.

    Parameters
    ----------
    method : {"speed"}
        Detection method (only the dilation-speed filter is implemented).
    column : str
        Column that receives the flags. The default overwrites ``in_blink``, so that :func:`pad_blinks` pads the
        detected stretches; use another name (e.g. ``"blink_speed"``) to compare with tracker blinks.

    Returns
    -------
    DataFrame
        The samples with the boolean ``column`` (invalid or speed outlier), ``speed_outlier`` (the widened speed
        outliers alone) and the trial's speed threshold in ``speed_threshold``.
    """
    if method != "speed":
        raise ValueError("detect_blinks: only method='speed' is implemented")
    check_columns(samples, ["reader", "trial", "time", "pupil"], "detect_blinks")
    s = sort_trials(samples)
    hz = sampling_rate(s)
    w = max(ms_to_samples(smooth_ms, hz), 1)
    k = ms_to_samples(pad_ms, hz)
    raw = s["pupil_raw"].to_numpy(float) if "pupil_raw" in s.columns else s["pupil"].to_numpy(float)
    lo, hi = pupil_range
    invalid = ~np.isfinite(raw) | (raw < lo) | (raw > hi)
    flag = np.zeros(len(s), bool)
    spd_all = np.zeros(len(s), bool)
    thr_all = np.full(len(s), np.nan)
    for a, b in trial_slices(s):
        pf = np.where(~invalid[a:b], raw[a:b], np.nan)
        i = np.arange(b - a) // w
        n = int(i.max()) + 1
        cnt = np.bincount(i, np.isfinite(pf), n)
        tot = np.bincount(i, np.nan_to_num(pf), n)
        m = np.where(cnt > 0, tot / np.maximum(cnt, 1), np.nan)
        step_ms = w * 1000.0 / hz
        d = np.fmax(np.abs(np.diff(m, prepend=np.nan)), np.abs(np.diff(m, append=np.nan))) / step_ms
        dd = d[np.isfinite(d)]
        thr = np.median(dd) + mad_k * np.median(np.abs(dd - np.median(dd))) if dd.size else np.inf
        spd = dilate((np.nan_to_num(d, nan=0) > thr)[i], k)
        flag[a:b] = invalid[a:b] | spd
        spd_all[a:b] = spd
        thr_all[a:b] = thr
    out = s.copy()
    out[column] = flag
    out["speed_outlier"] = spd_all
    out["speed_threshold"] = thr_all
    return copy_attrs(s, out)


def detector_agreement(samples: pd.DataFrame, mad_k: float = 16, pad_ms: float = 50, smooth_ms: float = 10) -> pd.DataFrame:
    """Per trial, how the pupil-based detector (:func:`detect_blinks`) agrees with the tracker's padded blinks.

    ``samples`` must have passed :func:`pad_blinks` (tracker blinks padded). Returns one row per trial with
    pct_padded_caught (share of padded-blink samples that the detector flags), pct_outside (detector-flagged samples
    outside padded blinks, as % of all samples) and pct_speed (speed outliers, % of all samples): Supplementary Note S1.
    """
    check_columns(samples, ["blink_pad", "invalid"], "detector_agreement (run pad_blinks first)")
    d = detect_blinks(samples, mad_k=mad_k, pad_ms=pad_ms, smooth_ms=smooth_ms,
                      pupil_range=tuple((samples.attrs or {}).get("pupil_range", (100, 10000))), column="_flag")
    rows = []
    info = [c for c in ("reader", "item", "trial", "version") if c in d.columns]
    fl, sp, bp, inv = (d[c].to_numpy(bool) for c in ("_flag", "speed_outlier", "blink_pad", "invalid"))
    for a, b in trial_slices(d):
        r = {c: d[c].iat[a] for c in info}
        r.update(pct_padded_caught=100 * (fl[a:b] & bp[a:b]).sum() / max(bp[a:b].sum(), 1),
                 pct_outside=100 * (sp[a:b] & ~bp[a:b] & ~inv[a:b]).mean(), pct_speed=100 * sp[a:b].mean(),
                 speed_threshold=float(d["speed_threshold"].iat[a]))
        rows.append(r)
    return pd.DataFrame(rows)


def _fill_cubic(q: np.ndarray, a: int, b: int) -> bool:
    """Cubic-spline fill of q[a..b] through points one gap length before and after (Mathot et al., 2018)."""
    L = b - a + 1
    t1, t2, t3, t4 = a - 1 - L, a - 1, b + 1, b + 1 + L
    if t1 < 0 or t4 >= len(q) or not np.all(np.isfinite(q[[t1, t2, t3, t4]])):
        return False
    cs = CubicSpline([t1, t2, t3, t4], q[[t1, t2, t3, t4]])
    q[a:b + 1] = cs(np.arange(a, b + 1))
    return True


def interpolate(samples: pd.DataFrame, max_gap_ms: float = 1000, kind: str = "linear",
                column: str = "pupil_interp") -> pd.DataFrame:
    """Fill gaps in the cleaned pupil trace that last up to ``max_gap_ms`` (stage 3.2).

    Gaps at the start or end of a trial and longer gaps stay missing. ``kind="linear"`` joins the valid samples on
    either side of a gap; ``kind="cubic"`` fits a cubic spline through four points spaced one gap length apart, as
    described by Mathot et al. (2018), and falls back to linear where those points are missing.

    Returns
    -------
    DataFrame
        The samples with the filled trace in ``column`` (default ``pupil_interp``, so that ``pupil`` keeps the removal
        trace; pass ``column="pupil"`` to replace it).
    """
    if kind not in ("linear", "cubic"):
        raise ValueError("interpolate: kind must be 'linear' or 'cubic'")
    check_columns(samples, ["reader", "trial", "time", "pupil"], "interpolate")
    s = sort_trials(samples)
    hz = sampling_rate(s)
    maxgap = ms_to_samples(max_gap_ms, hz)
    p = s["pupil"].to_numpy(float)
    q = p.copy()
    for a0, b0 in trial_slices(s):
        seg = q[a0:b0]
        bad = ~np.isfinite(seg)
        if bad.all() or not bad.any():
            continue
        st, en = runs(bad)
        for a, b in zip(st, en):
            if a == 0 or b == len(seg) - 1 or (b - a + 1) > maxgap:
                continue
            if kind == "cubic" and _fill_cubic(seg, a, b):
                continue
            seg[a:b + 1] = np.interp(np.arange(a, b + 1), [a - 1, b + 1], [seg[a - 1], seg[b + 1]])
        q[a0:b0] = seg
    out = s.copy()
    out[column] = q
    return copy_attrs(s, out, interpolation=dict(max_gap_ms=max_gap_ms, kind=kind, column=column))


Loss = namedtuple("Loss", ["trials", "by_version"])


def data_loss(samples: pd.DataFrame, by: Optional[str] = "version") -> Loss:
    """Data loss and event rates per trial, and their summary by version (stages 3.2 and 3.6).

    Parameters
    ----------
    samples : DataFrame
        Samples after :func:`pad_blinks`.
    by : str or None
        Column to summarise by (reader means per level, then mean across readers, with a paired t-test of the
        difference when there are two levels).

    Returns
    -------
    Loss
        ``trials``: one row per trial with n_samples, duration_s, pct_invalid, pct_blink_pad (samples lost to the
        padding only), pct_valid, n_blinks, n_saccades, blink_rate and saccade_rate (per s).
        ``by_version``: the summary table (None if ``by`` is None).
    """
    check_columns(samples, ["reader", "trial", "time", "valid", "invalid", "blink_pad", "in_blink", "in_saccade"],
                  "data_loss (run pad_blinks first)")
    s = sort_trials(samples)
    t = s["time"].to_numpy(float)
    inv, pad, val = (s[c].to_numpy(bool) for c in ("invalid", "blink_pad", "valid"))
    bl, sa = s["in_blink"].to_numpy(bool), s["in_saccade"].to_numpy(bool)
    rows = []
    info = [c for c in ("reader", "item", "trial", "version", "eye") if c in s.columns]
    for a, b in trial_slices(s):
        dur = (t[b - 1] - t[a]) / 1000.0 if b - a > 1 else np.nan
        nb, ns = len(onsets(bl[a:b])), len(onsets(sa[a:b]))
        row = {c: s[c].iat[a] for c in info}
        row.update(n_samples=b - a, duration_s=dur, pct_invalid=100 * inv[a:b].mean(),
                   pct_blink_pad=100 * (pad[a:b] & ~inv[a:b]).mean(), pct_valid=100 * val[a:b].mean(),
                   n_blinks=nb, n_saccades=ns, blink_rate=nb / dur if dur else np.nan,
                   saccade_rate=ns / dur if dur else np.nan)
        rows.append(row)
    T = pd.DataFrame(rows)
    return Loss(T, summarise(T, by=by) if by else None)


def summarise(trials: pd.DataFrame, by: str = "version",
              columns: Iterable[str] = ("duration_s", "pct_invalid", "pct_blink_pad", "pct_valid", "blink_rate",
                                        "saccade_rate")) -> pd.DataFrame:
    """Reader means of trial-level ``columns`` per level of ``by``, averaged across readers, with paired tests."""
    cols = [c for c in columns if c in trials.columns]
    pr = trials.groupby(["reader", by])[cols].mean().unstack(by)
    levels = list(pr.columns.levels[1])
    rows = []
    for c in cols:
        r = {"measure": c}
        for lv in levels:
            r[str(lv)] = pr[(c, lv)].mean()
        if len(levels) == 2:
            a, b2 = pr[(c, levels[0])], pr[(c, levels[1])]
            d = (b2 - a).dropna()
            if len(d) > 1:
                tt = stats.ttest_1samp(d, 0)
                h = stats.t.ppf(0.975, len(d) - 1) * d.std(ddof=1) / np.sqrt(len(d))
                r.update(difference=d.mean(), lo=d.mean() - h, hi=d.mean() + h, p=tt.pvalue, n_readers=len(d),
                         contrast=f"{levels[1]} - {levels[0]}")
        rows.append(r)
    return pd.DataFrame(rows)


def exclude_trials(samples: pd.DataFrame, min_valid: float = 0.5, exclude=None, loss: Optional[pd.DataFrame] = None):
    """Drop trials with too few valid samples or listed for exclusion (stage 3.2, missing-data threshold).

    Parameters
    ----------
    samples : DataFrame
        Samples after :func:`pad_blinks`.
    min_valid : float
        Minimum share of valid samples (paper: 0.5, i.e. trials with more than half of their samples missing are
        excluded; 0.75 is the stricter check of Table 3).
    exclude : DataFrame, iterable of (reader, trial) or CSV path, optional
        Trials to drop for other reasons decided blind to version (our study: skimmed or incomplete reading).
    loss : DataFrame, optional
        The ``trials`` table of :func:`data_loss`, if already computed.

    Returns
    -------
    (DataFrame, DataFrame)
        The remaining samples, and one row per trial with ``excluded`` and ``reason`` columns.
    """
    T = loss if loss is not None else data_loss(samples, by=None).trials
    T = T.copy()
    T["reason"] = ""
    ex = _exclusion_keys(exclude)
    if ex:
        k = list(zip(T["reader"].astype(str), T["trial"].astype(str)))
        T.loc[[x in ex for x in k], "reason"] = "listed"
    low = T["pct_valid"] < 100 * min_valid
    T.loc[low & (T["reason"] == ""), "reason"] = f"valid < {100 * min_valid:g}%"
    T["excluded"] = T["reason"] != ""
    keep = T.loc[~T["excluded"], TRIAL_KEY].astype(str)
    s = samples
    kk = pd.MultiIndex.from_arrays([s["reader"].astype(str), s["trial"].astype(str)])
    mask = kk.isin(pd.MultiIndex.from_frame(keep))
    out = s[mask].reset_index(drop=True)
    return copy_attrs(samples, out, min_valid_trial=min_valid), T


def _exclusion_keys(exclude):
    if exclude is None:
        return set()
    if isinstance(exclude, str):
        exclude = pd.read_csv(exclude, dtype=str)
    if isinstance(exclude, pd.DataFrame):
        col = "trial" if "trial" in exclude.columns else "item"
        return set(zip(exclude["reader"].astype(str), exclude[col].astype(str)))
    return {(str(r), str(t)) for r, t in exclude}
