"""Stage 3.1, data level: binning samples, and comparing fixation averages with samples."""
from __future__ import annotations

from collections import namedtuple
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from ._utils import TRIAL_INFO, check_columns, copy_attrs, sampling_rate, sort_trials, trial_slices


def bin(samples: pd.DataFrame, bin_ms: float = 20, min_valid: float = 0.5) -> pd.DataFrame:  # noqa: A001
    """Average samples in time bins (stage 3.1; paper: 20 ms bins, at least half of their samples valid).

    Pupil size is averaged over valid samples (missing ones are skipped), as are gaze coordinates; an interpolated trace
    (``pupil_interp``) and a gaze-corrected trace are averaged over all their finite values. Bins keep their sample
    counts, so that reader means can weight them; ``ok`` marks bins with at least ``min_valid`` of their samples valid,
    and later stages use only those.

    Returns
    -------
    DataFrame
        One row per trial and bin: reader, item, trial, version, eye, time (bin start, ms from text onset), pupil,
        n_valid, n_samples, ok, gaze_x, gaze_y, pupil_interp (if present), trial_end and duration (ms from the first to
        the last sample of the trial). ``attrs`` record bin_ms, hz, min_valid and samples_per_bin.
    """
    check_columns(samples, ["reader", "trial", "time", "pupil"], "bin")
    s = sort_trials(samples)
    hz = sampling_rate(s)
    spb = bin_ms * hz / 1000.0
    t = s["time"].to_numpy(float)
    valid = s["valid"].to_numpy(bool) if "valid" in s.columns else np.isfinite(s["pupil"].to_numpy(float))
    p = s["pupil"].to_numpy(float)
    cols = {"pupil": np.where(valid, p, np.nan)}
    for c in ("gaze_x", "gaze_y"):
        if c in s.columns:
            cols[c] = np.where(valid, s[c].to_numpy(float), np.nan)
    for c in ("pupil_interp", "pupil_corrected"):
        if c in s.columns:
            cols[c] = s[c].to_numpy(float)
    parts = []
    info = [c for c in TRIAL_INFO if c in s.columns]
    for a, b in trial_slices(s):
        tt = t[a:b]
        bi = np.floor(tt / bin_ms).astype(np.int64)
        keep = bi >= 0
        if not keep.any():
            continue
        bi0 = bi[keep]
        nb = int(bi0.max()) + 1
        d = {"time": np.arange(nb) * float(bin_ms)}
        nval = np.bincount(bi0, np.isfinite(cols["pupil"][a:b][keep]), nb)
        d["n_samples"] = np.bincount(bi0, minlength=nb)
        for c, v in cols.items():
            vv = v[a:b][keep]
            fin = np.isfinite(vv)
            tot = np.bincount(bi0[fin], vv[fin], nb)
            cnt = np.bincount(bi0[fin], minlength=nb)
            d[c] = np.where(cnt > 0, tot / np.maximum(cnt, 1), np.nan)
        d["n_valid"] = nval
        df = pd.DataFrame(d)
        df = df[df["n_samples"] > 0]
        for c in info:
            df[c] = s[c].iat[a]
        df["trial_end"] = s["trial_end"].iat[a] if "trial_end" in s.columns else tt[-1]
        df["duration"] = tt[-1] - tt[0]
        parts.append(df)
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    order = info + ["time", "pupil", "n_valid", "n_samples"] + [c for c in ("gaze_x", "gaze_y", "pupil_interp",
                                                                           "pupil_corrected") if c in out.columns]
    out = out[order + ["trial_end", "duration"]]
    out["ok"] = out["n_valid"].to_numpy(float) >= min_valid * spb
    attrs = dict(s.attrs or {})
    attrs.update(bin_ms=bin_ms, hz=hz, min_valid=min_valid, samples_per_bin=spb, level="bins")
    out.attrs = attrs
    return out


def retained_fixations(fixations: pd.DataFrame, min_fix_ms: float = 80, exclude_blinks: bool = True) -> pd.DataFrame:
    """Fixations of at least ``min_fix_ms`` that do not border a blink (the fixations retained in the paper)."""
    check_columns(fixations, ["reader", "trial", "start", "duration"], "retained_fixations")
    f = fixations[fixations["duration"] >= min_fix_ms]
    if exclude_blinks and "blink_around" in f.columns:
        f = f[~f["blink_around"].astype(str).str.upper().isin(["BEFORE", "AFTER", "BOTH"])]
    return f.reset_index(drop=True)


Levels = namedtuple("Levels", ["fixations", "summary"])


def compare_levels(samples: pd.DataFrame, fixations: pd.DataFrame, min_fix_ms: float = 80) -> Levels:
    """Compare the pupil value of each fixation with the mean of the valid samples inside it (stage 3.1).

    Parameters
    ----------
    samples : DataFrame
        Samples after :func:`pad_blinks` (one or more readers).
    fixations : DataFrame
        Fixation table (:func:`read_fixations`); retained fixations are those of at least ``min_fix_ms`` that do not
        border a blink.

    Returns
    -------
    Levels
        ``fixations``: one row per retained fixation with pupil (fixation report), pupil_samples (mean of the valid
        samples from fixation start to end) and n_valid. ``summary``: correlation r and mean absolute difference over
        fixations with both values, and coverage (retained fixation time / reading time, mean over trials).
    """
    s = sort_trials(samples)
    F = retained_fixations(fixations, min_fix_ms).copy()
    F["pupil_samples"] = np.nan
    F["n_valid"] = 0
    key_s = s["reader"].astype(str) + "\x1f" + s["trial"].astype(str)
    starts = {}
    for a, b in trial_slices(s):
        starts[key_s.iat[a]] = (a, b)
    t = s["time"].to_numpy(float)
    p = s["pupil"].to_numpy(float)
    key_f = (F["reader"].astype(str) + "\x1f" + F["trial"].astype(str)).to_numpy()
    ps = np.full(len(F), np.nan)
    nv = np.zeros(len(F), int)
    fs, fe = F["start"].to_numpy(float), F["end"].to_numpy(float)
    for i in range(len(F)):
        ab = starts.get(key_f[i])
        if ab is None:
            continue
        a, b = ab
        tt = t[a:b]
        i0, i1 = np.searchsorted(tt, fs[i]), np.searchsorted(tt, fe[i])
        seg = p[a:b][i0:i1]
        fin = np.isfinite(seg)
        nv[i] = int(fin.sum())
        if nv[i]:
            ps[i] = float(seg[fin].mean())
    F["pupil_samples"] = ps
    F["n_valid"] = nv
    ok = np.isfinite(F["pupil"]) & np.isfinite(F["pupil_samples"]) & (F["n_valid"] > 0)
    r = float(np.corrcoef(F.loc[ok, "pupil"], F.loc[ok, "pupil_samples"])[0, 1]) if ok.sum() > 2 else np.nan
    mad = float((F.loc[ok, "pupil"] - F.loc[ok, "pupil_samples"]).abs().mean()) if ok.any() else np.nan
    dur = s.groupby(["reader", "trial"])["time"].agg(lambda x: x.iloc[-1] - x.iloc[0])
    cov = F.groupby(["reader", "trial"])["duration"].sum()
    share = (cov / dur.reindex(cov.index)).dropna()
    summary = dict(r=r, mean_abs_diff=mad, n_fixations=int(ok.sum()), coverage=float(share.mean()) if len(share) else np.nan)
    return Levels(F, summary)


def fixation_means(fixations: pd.DataFrame, reader_means: pd.Series, window: Tuple[float, Optional[float]] = (500, 20000),
                   baseline: Tuple[float, float] = (0, 200), min_fix_ms: float = 80, name: str = "change_fixations") -> pd.DataFrame:
    """Trial means from fixation averages instead of samples (the fixation-level option of Table 4).

    The baseline is the mean pupil value of retained fixations that overlap the baseline window, the trial value the
    mean of retained fixations that start within ``window``; the change is expressed as % of the reader mean, as for
    samples.
    """
    F = retained_fixations(fixations, min_fix_ms)
    F = F[np.isfinite(F["pupil"])]
    b0, b1 = baseline
    a, z = window
    z = np.inf if z is None else z
    key = ["reader", "trial"]
    fb = F[(F["start"] < b1) & (F["start"] + F["duration"] > b0)].groupby(key)["pupil"].mean().rename("bs")
    fw = F[(F["start"] >= a) & (F["start"] < z)].groupby(key)["pupil"].mean().rename("m")
    T = pd.concat([fb, fw], axis=1).reset_index()
    rm = T["reader"].astype(str).map(reader_means.rename(index=str))
    T[name] = 100 * (T["m"] - T["bs"]) / rm
    info = [c for c in ("reader", "item", "trial", "version") if c in F.columns]
    T = T.merge(F[info].drop_duplicates(key), on=key, how="left")
    return T[info + [name]].dropna(subset=[name]).reset_index(drop=True)
