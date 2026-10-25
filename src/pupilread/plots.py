"""Stage 3.6, data quality checks and visualisation (black-and-white figures in the style of the paper)."""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd

from ._utils import ok_mask

LINESTYLES = ["-", (0, (4, 2)), (0, (1, 1.5)), (0, (6, 2, 1, 2))]


def _plt():
    import matplotlib
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
                         "axes.linewidth": 0.6})
    return matplotlib, plt


def _levels(df, by):
    return [] if by is None or by not in df.columns else sorted(df[by].dropna().unique(), key=str)


def plot_trials(bins: pd.DataFrame, column: str = "change", by: Optional[str] = "version", readers: Optional[Sequence] = None,
                max_readers: int = 6, ncols: int = 3):
    """Trial-level overlays: every trial's trace, one panel per reader, line style by ``by`` (stage 3.6).

    Overlays reveal residual artifacts that a summary statistic hides, such as spikes, gaps or implausible trajectories.
    """
    _, plt = _plt()
    rd = list(readers) if readers is not None else list(pd.unique(bins["reader"]))[:max_readers]
    nrows = int(np.ceil(len(rd) / ncols))
    fig, axs = plt.subplots(nrows, ncols, figsize=(2.4 * ncols, 1.8 * nrows), squeeze=False, sharex=True)
    lv = _levels(bins, by)
    ok = ok_mask(bins)
    for ax, r in zip(axs.ravel(), rd):
        b = bins[ok & (bins["reader"] == r)]
        for (_, tr), g in b.groupby(["reader", "trial"]):
            ls = LINESTYLES[lv.index(g[by].iat[0]) % 4] if lv else "-"
            ax.plot(g["time"] / 1000, g[column], color="k", lw=0.4, alpha=0.6, ls=ls)
        ax.set_title(f"Reader {r}", fontsize=7, loc="left")
        ax.axhline(0, color="k", lw=0.3)
    for ax in axs.ravel()[len(rd):]:
        ax.set_visible(False)
    for ax in axs[-1]:
        ax.set_xlabel("Time from text onset (s)")
    for ax in axs[:, 0]:
        ax.set_ylabel(column)
    fig.tight_layout()
    return fig


def plot_baselines(trials: pd.DataFrame, min_pct: float = 60, step: float = 2.5):
    """Histogram of baselines (% of the reader mean) with counts and log-scaled counts, and the cut-off (stage 3.3)."""
    _, plt = _plt()
    v = trials["baseline_pct"].dropna().to_numpy(float)
    edges = np.arange(np.floor(v.min() / 5) * 5, np.ceil(v.max() / 5) * 5 + 5, step)
    fig, axs = plt.subplots(1, 2, figsize=(6.8, 2.3))
    for ax, logc in zip(axs, (False, True)):
        ax.hist(v, bins=edges, color="#7a7a7a", edgecolor="white", linewidth=0.3, log=logc)
        ax.axvline(min_pct, color="k", lw=0.6, ls=":")
        ax.set_xlabel("Baseline pupil size (% of reader mean)")
        ax.set_ylabel("Trials" + (" (log scale)" if logc else ""))
    axs[0].set_title("Counts", fontsize=8)
    axs[1].set_title("Log counts", fontsize=8)
    fig.tight_layout()
    return fig


def plot_grand_mean(bins: pd.DataFrame, column: str = "change", by: Optional[str] = "version", bin_s: float = 1.0,
                    max_s: float = 40, min_readers: int = 20, min_baseline_pct: Optional[float] = 60, ax=None):
    """Grand-mean time course by version with 95% confidence intervals across readers (Figure 2B of the paper).

    Bins are averaged per reader in ``bin_s`` steps, then across readers; points with fewer than ``min_readers``
    readers are not drawn, so uneven trial lengths do not produce spurious divergence at the end of trials.
    """
    _, plt = _plt()
    ok = ok_mask(bins)
    b = bins[ok & (bins["time"] < max_s * 1000)].copy()
    if min_baseline_pct is not None and "baseline_pct" in b.columns:
        b = b[b["baseline_pct"] >= min_baseline_pct]
    b["sec"] = (b["time"] // (bin_s * 1000)).astype(int)
    keys = ([by] if by in b.columns else []) + ["reader", "sec"]
    r = b.groupby(keys)[column].mean().reset_index()
    if ax is None:
        fig, ax = plt.subplots(figsize=(3.4, 2.3))
    else:
        fig = ax.figure
    lv = _levels(r, by) or [None]
    out = []
    for i, level in enumerate(lv):
        z = r if level is None else r[r[by] == level]
        s = z.groupby("sec")[column].agg(["mean", "sem", "count"])
        s = s[s["count"] >= min_readers]
        x = (s.index + 0.5) * bin_s
        ax.fill_between(x, s["mean"] - 1.96 * s["sem"], s["mean"] + 1.96 * s["sem"], color="#c8c8c8", alpha=0.45, lw=0)
        ax.plot(x, s["mean"], color="k", lw=1.0, ls=LINESTYLES[i % 4], label=str(level) if level is not None else None)
        out.append(s.assign(level=level))
    ax.axhline(0, color="k", lw=0.4)
    ax.set_xlabel("Time from text onset (s)")
    ax.set_ylabel("Pupil change (% of reader mean)")
    if lv != [None]:
        ax.legend(fontsize=7)
    fig.grand_mean = pd.concat(out).reset_index()
    return fig


def plot_quality(trials: pd.DataFrame, by: str = "version",
                 measures: Sequence[str] = ("pct_valid", "pct_invalid", "pct_blink_pad", "blink_rate", "saccade_rate")):
    """Data loss and blink and saccade rates by version: reader means joined across versions (stage 3.6)."""
    _, plt = _plt()
    ms = [m for m in measures if m in trials.columns]
    fig, axs = plt.subplots(1, len(ms), figsize=(1.6 * len(ms), 2.2), squeeze=False)
    lv = _levels(trials, by)
    for ax, m in zip(axs[0], ms):
        pr = trials.groupby(["reader", by])[m].mean().unstack(by)[lv]
        for _, row in pr.iterrows():
            ax.plot(range(len(lv)), row.values, color="#9a9a9a", lw=0.5, marker="o", ms=2)
        ax.plot(range(len(lv)), pr.mean().values, color="k", lw=1.2, marker="o", ms=3)
        ax.set_xticks(range(len(lv)))
        ax.set_xticklabels([str(x) for x in lv], rotation=30, fontsize=6.5)
        ax.set_title(m, fontsize=7)
    fig.tight_layout()
    return fig


def plot_gaze(bins: pd.DataFrame, by: str = "version", relative_to_baseline: bool = True, window=(500, 20000),
              baseline_window=(0, 200)):
    """Mean gaze position by version (stage 3.6): reader means of horizontal and vertical gaze, optionally relative to
    the gaze position in the baseline window, which shows where versions differ in the gaze artifact (Section 3.4)."""
    _, plt = _plt()
    ok = ok_mask(bins)
    b = bins[ok].copy()
    key = ["reader", "trial"]
    w = b[(b["time"] >= window[0]) & (b["time"] < window[1])].groupby(key)[["gaze_x", "gaze_y"]].mean()
    if relative_to_baseline:
        bb = b[(b["time"] >= baseline_window[0]) & (b["time"] < baseline_window[1])].groupby(key)[["gaze_x", "gaze_y"]].mean()
        w = w - bb
    info = bins.drop_duplicates(key).set_index(key)[[by]]
    w = w.join(info).reset_index()
    pr = w.groupby(["reader", by])[["gaze_x", "gaze_y"]].mean().reset_index()
    fig, ax = plt.subplots(figsize=(3.0, 2.6))
    lv = _levels(pr, by)
    marks = ["o", "s", "^", "D"]
    for i, level in enumerate(lv):
        z = pr[pr[by] == level]
        ax.scatter(z["gaze_x"], z["gaze_y"], s=8, facecolor="none" if i else "k", edgecolor="k", marker=marks[i % 4],
                   lw=0.6, label=str(level))
    ax.invert_yaxis()
    ax.set_xlabel("Horizontal gaze" + (" relative to baseline" if relative_to_baseline else "") + " (px)")
    ax.set_ylabel("Vertical gaze (px)")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.gaze_table = pr
    return fig
