"""Shared helpers: table conventions, trial slicing, run detection and dilation."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

#: Columns of the sample table that every reader function returns (Section 3 of the README).
SAMPLE_COLUMNS = ["reader", "item", "trial", "version", "eye", "time", "pupil", "gaze_x", "gaze_y",
                  "in_blink", "in_saccade", "trial_end"]
#: Columns that identify a trial.
TRIAL_KEY = ["reader", "trial"]
#: Trial-level columns carried along from samples to bins and trial tables.
TRIAL_INFO = ["reader", "item", "trial", "version", "eye"]


class PipelineOrderWarning(UserWarning):
    """Raised when stages are applied in an order that changes their meaning (e.g. gaze correction after baseline)."""


def check_columns(df: pd.DataFrame, columns, where: str) -> None:
    """Raise a ValueError naming the function if any of ``columns`` is missing from ``df``."""
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"{where}: missing column(s) {missing}; available: {list(df.columns)}")


def copy_attrs(src: pd.DataFrame, dst: pd.DataFrame, **extra) -> pd.DataFrame:
    """Copy ``src.attrs`` to ``dst`` (pandas does not always propagate them) and add ``extra`` entries."""
    attrs = dict(getattr(src, "attrs", {}) or {})
    attrs.update(extra)
    dst.attrs = attrs
    return dst


def sampling_rate(samples: pd.DataFrame) -> float:
    """Sampling rate in Hz: ``samples.attrs['hz']`` if set, otherwise estimated from the median time step."""
    hz = (getattr(samples, "attrs", {}) or {}).get("hz")
    if hz:
        return float(hz)
    t = samples["time"].to_numpy(float)
    d = np.diff(t)
    d = d[(d > 0) & np.isfinite(d)]
    if d.size == 0:
        raise ValueError("cannot estimate the sampling rate: set samples.attrs['hz']")
    return float(round(1000.0 / np.median(d), 3))


def ms_to_samples(ms: float, hz: float) -> int:
    """Number of samples spanning ``ms`` milliseconds at ``hz``."""
    return int(round(ms * hz / 1000.0))


def sort_trials(df: pd.DataFrame, time_col: str = "time") -> pd.DataFrame:
    """Return ``df`` sorted by reader, trial and time (stable), keeping attrs."""
    keys = [c for c in ("reader", "trial", time_col) if c in df.columns]
    if not keys:
        return df
    out = df.sort_values(keys, kind="mergesort").reset_index(drop=True)
    return copy_attrs(df, out)


def trial_slices(df: pd.DataFrame):
    """Yield ``(start, stop)`` row ranges of consecutive rows sharing reader and trial (df must be sorted)."""
    if len(df) == 0:
        return
    r = pd.factorize(df["reader"].astype(str))[0]
    t = pd.factorize(df["trial"].astype(str))[0]
    change = np.flatnonzero((np.diff(r) != 0) | (np.diff(t) != 0)) + 1
    bounds = np.r_[0, change, len(df)]
    for a, b in zip(bounds[:-1], bounds[1:]):
        yield int(a), int(b)


def runs(mask: np.ndarray):
    """Start and end indices (inclusive) of runs of True in a boolean array."""
    m = np.asarray(mask, bool).astype(np.int8)
    d = np.diff(np.r_[0, m, 0])
    return np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1


def dilate(mask: np.ndarray, k: int) -> np.ndarray:
    """Widen every run of True in ``mask`` by ``k`` elements on both sides (no overflow for long runs)."""
    m = np.asarray(mask, bool)
    if k <= 0 or not m.any():
        return m.copy()
    c = np.r_[0, np.cumsum(m, dtype=np.int64)]
    n = len(m)
    i = np.arange(n)
    lo = np.clip(i - k, 0, n)
    hi = np.clip(i + k + 1, 0, n)
    return (c[hi] - c[lo]) > 0


def onsets(mask: np.ndarray) -> np.ndarray:
    """Indices where a run of True starts."""
    return runs(mask)[0]


def trial_table(df: pd.DataFrame, extra=()) -> pd.DataFrame:
    """One row per trial with the identifying columns present in ``df`` (and any ``extra`` constant columns)."""
    cols = [c for c in TRIAL_INFO + list(extra) if c in df.columns]
    return df.drop_duplicates(TRIAL_KEY)[cols].reset_index(drop=True)


def warn_order(message: str) -> None:
    warnings.warn(message, PipelineOrderWarning, stacklevel=3)


def as_list(x):
    if x is None:
        return []
    if isinstance(x, (list, tuple, set)):
        return list(x)
    return [x]


def ok_mask(bins: pd.DataFrame, min_valid=None) -> np.ndarray:
    """Boolean mask of bins with enough valid samples: the ``ok`` column, or ``min_valid`` (share) if given."""
    if min_valid is None:
        if "ok" in bins.columns:
            return bins["ok"].to_numpy(bool) & np.isfinite(bins["pupil"].to_numpy(float))
        min_valid = (bins.attrs or {}).get("min_valid", 0.5)
    spb = (bins.attrs or {}).get("samples_per_bin")
    if spb is None:
        raise ValueError("bins.attrs['samples_per_bin'] is missing; create bins with pupilread.bin()")
    return (bins["n_valid"].to_numpy(float) >= min_valid * spb) & np.isfinite(bins["pupil"].to_numpy(float))
