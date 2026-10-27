"""Stage 3.7, hand-over to R: the trial table and the binned trace that lmm.R, gamm.R and multiverse.R read.

The package stops here because crossed random effects (lme4) and GAMMs with an AR1 term (mgcv) are best fitted in R.
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import warnings
from typing import Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ._utils import check_columns, ok_mask
from ._version import __version__

R_SCRIPTS = ("lmm.R", "gamm.R", "multiverse.R")


def r_script_path(name: str) -> str:
    """Path of one of the R scripts installed with the package (``lmm.R``, ``gamm.R`` or ``multiverse.R``)."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "R", name)
    if not os.path.exists(p):
        raise FileNotFoundError(p)
    return p


def _contrast(version: pd.Series, reference: Optional[str]):
    lv = sorted(pd.unique(version.dropna().astype(str)))
    if len(lv) != 2:
        warnings.warn(f"export_for_r: 'contrast' needs exactly two versions, found {lv}; the column is left missing")
        return pd.Series(np.nan, index=version.index), lv, None
    ref = str(reference) if reference is not None else lv[0]
    if ref not in lv:
        raise ValueError(f"export_for_r: reference {ref!r} is not one of the versions {lv}")
    other = [x for x in lv if x != ref][0]
    return (version.astype(str) == other).astype(int), lv, ref


def gamm_bins(bins: pd.DataFrame, bin_ms: float = 100, window: Tuple[float, float] = (500, 20000),
              column: str = "change") -> pd.DataFrame:
    """Average the 20 ms bins of every trial in ``bin_ms`` bins within ``window`` (the trace for gamm.R).

    Only bins with enough valid samples enter (the ``ok`` column of :func:`bin`); pupil change and gaze position are
    their means. ``time`` is the bin centre in seconds from text onset.
    """
    check_columns(bins, ["reader", "trial", "time", column], "gamm_bins (run baseline first)")
    ok = ok_mask(bins) & np.isfinite(bins[column].to_numpy(float))
    t = bins["time"].to_numpy(float)
    m = ok & (t >= window[0]) & (t < window[1])
    keys = [c for c in ("reader", "item", "trial", "version", "eye") if c in bins.columns]
    extra = [c for c in ("baseline_pct",) if c in bins.columns]
    W = bins.loc[m, keys + extra + ["time", column, "gaze_x", "gaze_y"]].copy()
    W["t100"] = (W["time"] // bin_ms) * bin_ms
    g = W.groupby(keys + ["t100"], sort=False, dropna=False)
    G = g.agg(pupil_change=(column, "mean"), gaze_x=("gaze_x", "mean"), gaze_y=("gaze_y", "mean"),
              n_bins=(column, "size")).reset_index()
    if extra:
        G = G.merge(W.drop_duplicates(["reader", "trial"])[["reader", "trial"] + extra], on=["reader", "trial"], how="left")
    G["time"] = (G["t100"] + bin_ms / 2) / 1000.0
    G = G.drop(columns="t100").sort_values(["reader", "trial", "time"], kind="mergesort").reset_index(drop=True)
    first = ~G.duplicated(["reader", "trial"])
    G["trial_start"] = first.astype(int)
    cols = keys + ["time", "pupil_change", "gaze_x", "gaze_y", "trial_start", "n_bins"] + extra
    return G[cols]


def export_for_r(trials: pd.DataFrame, bins: pd.DataFrame, folder: str = "for_R", bin_ms: float = 100,
                 window: Tuple[float, float] = (500, 20000), reference: Optional[str] = None, scripts: bool = True,
                 options: Optional[pd.DataFrame] = None, config=None) -> dict:
    """Write the files for the models in R (stage 3.7): trials.csv, bins.csv and, for options tables, options.csv.

    Parameters
    ----------
    trials : DataFrame
        One row per trial: :func:`trial_means` output or :func:`options_table`. Must contain reader, item, version and
        baseline_pct; ``change_0_20s`` (the paper's primary measure) is what ``lmm.R`` models.
    bins : DataFrame
        Bins after :func:`baseline` (20 ms), averaged here into ``bin_ms`` bins within ``window`` for ``gamm.R``.
    folder : str
        Output folder (created if needed).
    bin_ms : float
        Bin size of the trace for the time-course model (paper: 100 ms).
    window : (start, end)
        Time window of the trace, ms from text onset (paper: 500 to 20,000 ms).
    reference : str, optional
        Version coded 0 in the ``contrast`` column (default: the first version in alphabetical order, which is
        "non-simplified" in the paper); the other version is coded 1.
    scripts : bool
        Copy lmm.R, gamm.R and multiverse.R into ``folder``, so that they run there without editing.
    options : DataFrame, optional
        Model table for multiverse.R (default: ``trials.attrs["options"]`` from :func:`options_table`).

    Returns
    -------
    dict
        Paths of the files written.

    Notes
    -----
    All trials with a baseline are written; the R scripts keep those whose baseline is at least ``MIN_BASE`` (60) %
    of the reader mean, as in the paper. In an options table each option column already leaves out the trials that
    the option excludes.
    """
    check_columns(trials, ["reader", "item", "version", "baseline_pct"], "export_for_r(trials)")
    os.makedirs(folder, exist_ok=True)
    min_pct = (dict(config).get("low_baselines", {}) or {}).get("min_pct", 60) if config is not None else 60
    T = trials.copy()
    T = T[np.isfinite(T["baseline_pct"].astype(float))]
    T["contrast"], levels, ref = _contrast(T["version"], reference)
    front = [c for c in ("reader", "item", "trial", "version", "contrast", "eye", "baseline_pct") if c in T.columns]
    T = T[front + [c for c in T.columns if c not in front]]
    files = {}
    p = os.path.join(folder, "trials.csv")
    T.to_csv(p, index=False)
    files["trials.csv"] = p
    G = gamm_bins(bins, bin_ms=bin_ms, window=window)
    G["contrast"], _, _ = _contrast(G["version"], ref)
    G = G[[c for c in ("reader", "item", "trial", "version", "contrast", "eye") if c in G.columns]
          + [c for c in G.columns if c not in ("reader", "item", "trial", "version", "contrast", "eye")]]
    p = os.path.join(folder, "bins.csv")
    G.to_csv(p, index=False)
    files["bins.csv"] = p
    spec = options
    if spec is None and (trials.attrs or {}).get("options"):
        spec = pd.DataFrame(trials.attrs["options"])
    if spec is not None and len(spec):
        spec = spec[spec["column"].isin(T.columns)]
        p = os.path.join(folder, "options.csv")
        spec.to_csv(p, index=False)
        files["options.csv"] = p
    if scripts:
        for s in R_SCRIPTS:
            try:
                dst = os.path.join(folder, s)
                shutil.copyfile(r_script_path(s), dst)
                files[s] = dst
            except FileNotFoundError:
                warnings.warn(f"export_for_r: R script {s} not found in the installation")
    meta = {"pupilread": __version__, "written": datetime.datetime.now().isoformat(timespec="seconds"),
            "versions": levels, "reference (contrast = 0)": ref, "trials": int(len(T)),
            "min_baseline_pct": min_pct,
            "trials_analysed": int((T["baseline_pct"] >= (min_pct if min_pct is not None else -np.inf)).sum()),
            "bins": int(len(G)), "bin_ms": bin_ms, "window_ms": list(window),
            "bins_attrs": {k: (list(v) if isinstance(v, tuple) else v) for k, v in (bins.attrs or {}).items()
                           if isinstance(v, (int, float, str, list, tuple, dict, type(None)))}}
    if config is not None:
        meta["config"] = {k: v for k, v in dict(config).items() if k != "_resolved"}
    p = os.path.join(folder, "pupilread.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1, default=str)
    files["pupilread.json"] = p
    return files
