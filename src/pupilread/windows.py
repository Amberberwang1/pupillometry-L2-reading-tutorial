"""Stage 3.5, trial length and events: time-matched trial means and event-locked responses."""
from __future__ import annotations

from collections import namedtuple
from typing import Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

from ._utils import TRIAL_KEY, check_columns, ok_mask, runs, sort_trials, trial_slices
from .baseline import reader_means as _reader_means


def window_name(window, cut_before_keypress_ms: float = 0, prefix: str = "change") -> str:
    """Column name for a trial measure: ``change_0_20s`` for the paper's 0.5-20 s window, else e.g. ``change_2_20s``."""
    a, b = window
    if b is None:
        core = "whole_trial" if a == 500 else f"{a / 1000:g}s_to_end"
    elif a == 500 and b == 20000:
        core = "0_20s"
    else:
        core = f"{a / 1000:g}_{b / 1000:g}s".replace(".", "p")
    name = f"{prefix}_{core}"
    if cut_before_keypress_ms:
        name += f"_cut{cut_before_keypress_ms / 1000:g}s"
    return name


def trial_means(bins: pd.DataFrame, window: Tuple[float, Optional[float]] = (500, 20000), cut_before_keypress_ms: float = 0,
                min_valid: Optional[float] = None, column: str = "change", name: Optional[str] = None) -> pd.DataFrame:
    """One value per trial: the mean change in a time window matched across versions (stage 3.5).

    Parameters
    ----------
    bins : DataFrame
        Bins after :func:`baseline`.
    window : (start, end)
        Window in ms from text onset (paper: 500 to 20,000 ms, the same in every version). ``end=None`` runs to the end
        of the trial (the whole-trial mean, which compares different portions of the slow drift when trial length
        differs between versions).
    cut_before_keypress_ms : float
        Leave out the last part of each trial, to check the run-up to the end-of-reading key press (Section 3.5).
    min_valid : float, optional
        Share of valid samples a bin needs (default: the ``ok`` column of :func:`bin`).
    column : str
        Bin column to average (default ``change``).
    name : str, optional
        Name of the output column (default from :func:`window_name`, ``change_0_20s`` for the paper's window).

    Returns
    -------
    DataFrame
        One row per trial with reader, item, trial, version, eye, baseline_pct and the trial measure. Trials without
        valid bins in the window or without a baseline are missing.
    """
    check_columns(bins, ["reader", "trial", "time", column], "trial_means (run baseline first)")
    name = name or window_name(window, cut_before_keypress_ms, "change" if column == "change" else column)
    bin_ms = float((bins.attrs or {}).get("bin_ms", 20))
    ok = ok_mask(bins, min_valid)
    t = bins["time"].to_numpy(float)
    a, b = window
    m = ok & (t >= a)
    if b is not None:
        m &= t < b
    if cut_before_keypress_ms:
        check_columns(bins, ["duration"], "trial_means(cut_before_keypress_ms)")
        m &= (t + bin_ms) <= (bins["duration"].to_numpy(float) - cut_before_keypress_ms)
    sel = bins.loc[m, TRIAL_KEY + [column]]
    v = sel.groupby(TRIAL_KEY, sort=False)[column].mean().rename(name).reset_index()
    info = [c for c in ("reader", "item", "trial", "version", "eye", "baseline_pct") if c in bins.columns]
    T = bins.drop_duplicates(TRIAL_KEY)[info].merge(v, on=TRIAL_KEY, how="left")
    if "baseline_pct" in T.columns:
        T = T[np.isfinite(T["baseline_pct"])]
    return T.dropna(subset=[name]).reset_index(drop=True)


Events = namedtuple("Events", ["summary", "by_reader"])


def _summarise(by_reader: pd.DataFrame, level_col: Optional[str]) -> pd.DataFrame:
    keys = ([level_col] if level_col else []) + ["lag"]
    g = by_reader.groupby(keys)
    s = g["pct"].agg(["mean", "sem", "count"]).rename(columns={"count": "n_readers"})
    s["pooled"] = g["sum"].sum() / g["n"].sum()
    if "reader_mean" in by_reader.columns:
        grand = by_reader.drop_duplicates("reader")["reader_mean"].mean()
        s["pooled_pct"] = 100 * s["pooled"] / grand
    s["n_events"] = g["n_events"].sum() if "n_events" in by_reader.columns else np.nan
    return s.reset_index()


EVENT_WINDOWS = {"blink": (-200, 2000), "saccade": (-200, 2000), "return_sweep": (-300, 1000), "table": (-200, 2000)}


def event_response(data: pd.DataFrame, event: Union[str, pd.DataFrame] = "blink", window: Optional[Tuple[float, float]] = None,
                   by: Optional[str] = "version", saccades: Optional[pd.DataFrame] = None, baseline_ms: float = 100,
                   types: Sequence[str] = ("return sweep",), means: Optional[pd.Series] = None,
                   lag_ms: float = 1.0) -> Events:
    """Event-locked pupil responses (stage 3.5; Figure 2C-D of the paper).

    Parameters
    ----------
    data : DataFrame
        Samples after :func:`pad_blinks` for ``event="blink"``, ``"saccade"`` or an event table; bins (:func:`bin`) for
        ``event="return_sweep"``.
    event : {"blink", "saccade", "return_sweep"} or DataFrame
        ``blink``: locked to the last blink sample; baseline the ``baseline_ms`` before blink onset minus the padding,
        so that the blink's own response is measured. ``saccade``: locked to saccade onset, baseline just before it.
        ``return_sweep``: landing-locked bins of the saccades of ``types`` in ``saccades`` (:func:`saccade_steps`),
        relative to the pupil before saccade onset, as in Figure 2C. A DataFrame with reader, trial and time (ms from
        text onset) locks the samples to those events.
    window : (start, end), optional
        Lags in ms around the event (default: -200 to 2,000 ms for blinks, saccades and event tables, as in Figure 2D;
        -300 to 1,000 ms for return sweeps, as in Figure 2C).
    by : str or None
        Column to split by (``version``; ``eye`` for return sweeps).
    lag_ms : float
        Width of the lag bins of the output (samples are pooled within them), so that readers recorded at different
        sampling rates share one time axis.

    Returns
    -------
    Events
        ``summary``: per level and lag, the mean and SEM across readers of each reader's mean response (% of the
        reader mean), the number of readers, ``pooled`` (all events pooled, raw units) and ``pooled_pct`` (pooled, as
        % of the average reader mean, as in Figure 2D).
        ``by_reader``: per reader, level and lag the sum, count and mean of the responses.
    """
    key = "return_sweep" if isinstance(event, str) and event in ("return_sweep", "return sweep", "saccade_steps") else (
        event if isinstance(event, str) else "table")
    window = tuple(window) if window is not None else EVENT_WINDOWS.get(key, (-200, 2000))
    if key == "return_sweep":
        return _saccade_locked_bins(data, saccades, window, by or "eye", types, means)
    check_columns(data, ["reader", "trial", "time", "pupil"], "event_response")
    s = sort_trials(data)
    rm = means if means is not None else _valid_means(s)
    hz = float((s.attrs or {}).get("hz") or 1000.0)
    step = 1000.0 / hz
    lags = np.arange(int(round(window[0] / step)), int(round(window[1] / step)) + 1)
    pad = int(round(float((s.attrs or {}).get("pad_ms", 0)) / step))
    nb = int(round(baseline_ms / step))
    p = s["pupil"].to_numpy(float)
    level_col = by if (by and by in s.columns) else None
    acc = {}
    ev_tab = None
    if isinstance(event, pd.DataFrame):
        ev_tab = event.copy()
        ev_tab["reader"] = ev_tab["reader"].astype(str)
        ev_tab["trial"] = ev_tab["trial"].astype(str)
    elif event not in ("blink", "saccade"):
        raise ValueError("event_response: event must be 'blink', 'saccade', 'return_sweep' or a DataFrame")
    for a0, b0 in trial_slices(s):
        n = b0 - a0
        seg = p[a0:b0]
        reader = s["reader"].iat[a0]
        lev = s[level_col].iat[a0] if level_col else "all"
        if isinstance(event, str):
            flag = s["in_blink" if event == "blink" else "in_saccade"].to_numpy(bool)[a0:b0]
            st, en = runs(flag)
            locks, bases = (en, st - pad) if event == "blink" else (st, st)
        else:
            tt = s["time"].to_numpy(float)[a0:b0]
            e = ev_tab[(ev_tab["reader"] == str(reader)) & (ev_tab["trial"] == str(s["trial"].iat[a0]))]
            locks = np.searchsorted(tt, e["time"].to_numpy(float))
            bases = locks
        for i0, ib in zip(locks, bases):
            lo, hi = i0 + lags[0], i0 + lags[-1]
            if lo < 0 or hi >= n or ib - nb < 0:
                continue
            w = seg[ib - nb:ib]
            if not np.isfinite(w).any():
                continue
            bl = np.nanmean(w)
            vals = seg[lo:hi + 1] - bl
            fin = np.isfinite(vals)
            k = (reader, lev)
            if k not in acc:
                acc[k] = [np.zeros(len(lags)), np.zeros(len(lags)), 0]
            acc[k][0][fin] += vals[fin]
            acc[k][1][fin] += 1
            acc[k][2] += 1
    out_lag = lags * step
    if lag_ms:
        out_lag = np.floor(np.round(out_lag / lag_ms, 6)) * lag_ms
    ulag, inv = np.unique(out_lag, return_inverse=True)
    rows = []
    for (reader, lev), (sm, ct, ne) in acc.items():
        r_m = float(rm.get(reader, np.nan)) if hasattr(rm, "get") else np.nan
        S_ = np.bincount(inv, sm, len(ulag))
        C_ = np.bincount(inv, ct, len(ulag))
        for lg, a_, c_ in zip(ulag, S_, C_):
            if c_ > 0:
                rows.append({"reader": reader, (level_col or "level"): lev, "lag": float(lg), "sum": a_, "n": c_,
                             "mean": a_ / c_, "pct": 100 * (a_ / c_) / r_m, "n_events": ne, "reader_mean": r_m})
    BR = pd.DataFrame(rows)
    if BR.empty:
        return Events(pd.DataFrame(), BR)
    return Events(_summarise(BR, level_col or "level"), BR)


def _valid_means(samples: pd.DataFrame) -> pd.Series:
    v = samples[["reader", "pupil"]]
    return v[np.isfinite(v["pupil"])].groupby("reader")["pupil"].mean()


def _saccade_locked_bins(bins, saccades, window, by, types, means):
    if saccades is None:
        raise ValueError("event_response(event='return_sweep') needs saccades=saccade_steps(...)")
    bin_ms = float((bins.attrs or {}).get("bin_ms", 20))
    rm = means if means is not None else _reader_means(bins)
    ok = ok_mask(bins)
    B = bins.loc[ok, ["reader", "trial", "time", "pupil"]].copy()
    B["v"] = 100 * B["pupil"].to_numpy(float) / B["reader"].map(rm).to_numpy(float)
    lags = np.arange(window[0], window[1] + 1, bin_ms)
    S = saccades[saccades["type"].isin(types) & np.isfinite(saccades["ref"])]
    acc = {}
    for (r, tr), s in S.groupby(["reader", "trial"], sort=False):
        b = B[(B["reader"] == r) & (B["trial"] == tr)]
        if b.empty:
            continue
        idx = (b["time"].to_numpy(float) // bin_ms).astype(int)
        arr = np.full(idx.max() + 60, np.nan)
        arr[idx] = b["v"].to_numpy(float)
        for q in s.itertuples(index=False):
            i0 = int(np.floor((q.landing + window[0]) / bin_ms))
            ii = np.arange(i0, i0 + len(lags) + 5)
            ii = ii[(ii >= 0) & (ii < len(arr))]
            rel = np.round((ii * bin_ms + bin_ms / 2 - q.landing) / bin_ms).astype(int) * bin_ms
            keep = (rel >= window[0]) & (rel <= window[1]) & np.isfinite(arr[ii])
            k = (r, getattr(q, by) if by in s.columns else "all", q.type)
            if k not in acc:
                acc[k] = [np.zeros(len(lags)), np.zeros(len(lags)), 0]
            j = ((rel[keep] - window[0]) // bin_ms).astype(int)
            np.add.at(acc[k][0], j, arr[ii][keep] - q.ref)
            np.add.at(acc[k][1], j, 1)
            acc[k][2] += 1
    rows = []
    for (r, lev, ty), (sm, ct, ne) in acc.items():
        for lg, a_, c_ in zip(lags, sm, ct):
            if c_ > 0:
                rows.append({"reader": r, by: lev, "type": ty, "lag": float(lg), "sum": a_, "n": c_, "mean": a_ / c_,
                             "pct": a_ / c_, "n_events": ne})
    BR = pd.DataFrame(rows)
    if BR.empty:
        return Events(pd.DataFrame(), BR)
    g = BR.groupby([by, "type", "lag"])
    summ = g["pct"].agg(["mean", "sem", "count"]).rename(columns={"count": "n_readers"})
    summ["n_events"] = g["n_events"].sum()
    return Events(summ.reset_index(), BR)
