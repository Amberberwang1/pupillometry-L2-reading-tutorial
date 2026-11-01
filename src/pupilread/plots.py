"""Stage 3.6, data quality checks and visualisation (black-and-white figures in the style of the paper)."""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ._utils import ok_mask, sampling_rate, sort_trials

LINESTYLES = ["-", (0, (4, 2)), (0, (1, 1.5)), (0, (6, 2, 1, 2))]


def _plt():
    import matplotlib
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
                         "axes.linewidth": 0.6})
    return matplotlib, plt


def _levels(df, by):
    return [] if by is None or by not in df.columns else sorted(df[by].dropna().unique(), key=str)


def plot_overlays(bins: pd.DataFrame, column: str = "change", by: Optional[str] = "version", readers: Optional[Sequence] = None,
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


def _runs(mask):
    """Start and end (exclusive) indices of every run of True in ``mask``."""
    d = np.diff(np.r_[0, np.asarray(mask, bool).astype(np.int8), 0])
    return np.flatnonzero(d == 1), np.flatnonzero(d == -1)


def plot_trial(samples: pd.DataFrame, trial, reader=None, pad_ms: float = 100, bin_ms: float = 20,
               window: Tuple[float, float] = (0, 200), pupil_range: Tuple[float, float] = (100, 10000),
               min_valid: float = 0.5, reader_mean: Optional[float] = None,
               xlim: Optional[Tuple[float, float]] = None, zoom: Optional[Tuple[float, float]] = None):
    """One trial at four stages of the pipeline (stages 3.1 to 3.3; Figure 2 of the paper).

    (A) The raw samples, with the blinks the tracker marked shaded. (B) The samples after each blink is padded by
    ``pad_ms`` and the padded and invalid samples are removed (:func:`pad_blinks`), with the padded stretches shaded.
    (C) The ``bin_ms`` bins (:func:`bin`); with ``zoom``, panel C instead enlarges a short stretch, boxed in panel B,
    and draws the samples (grey line) with their bin means (black bars). (D) The bins after subtractive baseline
    correction over ``window``, as a percentage of the reader mean (:func:`baseline`), with the baseline window
    shaded. The panels run the package's own functions, so they show exactly what the pipeline does to the trial.

    Parameters
    ----------
    samples : DataFrame
        Sample table (:func:`read_eyelink`, :func:`read_csv`), raw or already padded (``pupil_raw`` is then redrawn
        and padded again with ``pad_ms``). Pass all of a reader's trials, so that the reader mean of panel D covers them.
    trial : int
        Trial to draw (TRIAL_INDEX).
    reader : optional
        Reader to draw, if ``samples`` holds several readers.
    pad_ms, bin_ms, window, pupil_range, min_valid
        Settings of :func:`pad_blinks`, :func:`bin` and :func:`baseline` (defaults: the paper's).
    reader_mean : float, optional
        Denominator of panel D. By default the mean of the reader's valid samples in ``samples`` after padding
        (:func:`reader_means`); the pipeline takes it over the trials kept after the exclusions.
    xlim : (start, end), optional
        Time range in seconds from text onset (default: the whole trial).
    zoom : (start, end), optional
        A short stretch in seconds, such as (3.0, 3.5), for panel C to enlarge. Over a whole trial, the samples and
        their bin means look alike, because binning changes pupil size by only a few units; enlarged, the difference
        shows (Figure 2 of the paper uses (3.0, 3.5)).

    Returns
    -------
    matplotlib Figure
        Four stacked panels sharing the time axis; ``fig.trial_data`` holds the samples and bins drawn.
    """
    from .baseline import baseline, reader_means
    from .blinks import pad_blinks
    from .levels import bin as to_bins

    _, plt = _plt()
    readers = list(pd.unique(samples["reader"]))
    if reader is None:
        if len(readers) != 1:
            raise ValueError("plot_trial: samples hold several readers; pass reader=")
        reader = readers[0]
    s = samples[samples["reader"] == reader]
    if len(s) == 0:
        raise ValueError(f"plot_trial: no samples for reader {reader!r}")
    if not (s["trial"] == trial).any():
        raise ValueError(f"plot_trial: reader {reader!r} has no trial {trial!r}")
    if "pupil_raw" in s.columns:                      # padded already: start again from the samples as recorded
        s = s.drop(columns=[c for c in ("pupil", "invalid", "blink_pad", "valid") if c in s.columns])
        s = s.rename(columns={"pupil_raw": "pupil"})
    s = s.copy()
    s.attrs = dict(samples.attrs)
    padded = pad_blinks(s, pad_ms=pad_ms, pupil_range=pupil_range)
    bins = to_bins(padded, bin_ms=bin_ms, min_valid=min_valid)
    rm = float(reader_mean) if reader_mean is not None else float(reader_means(bins).iloc[0])
    based = baseline(bins, window=window, method="subtractive", scale="reader_mean",
                     means=pd.Series({reader: rm}))
    st = sort_trials(padded[padded["trial"] == trial])
    bt = based[based["trial"] == trial].sort_values("time")
    t = st["time"].to_numpy(float) / 1000
    tb = bt["time"].to_numpy(float) / 1000
    okb = ok_mask(bt)
    hz = sampling_rate(st)
    fig = plt.figure(figsize=(6.6, 6.4 if zoom is None else 7.0))
    gs = fig.add_gridspec(4, 1, hspace=0.45 if zoom is None else 0.55)
    axs = [fig.add_subplot(gs[0])]
    for i in (1, 2, 3):                             # A, B and D share the time axis; C too, unless it is enlarged
        axs.append(fig.add_subplot(gs[i], sharex=None if (i == 2 and zoom is not None) else axs[0]))
    for i in ((0, 1) if zoom is not None else (0, 1, 2)):
        axs[i].tick_params(labelbottom=False)
    shade = "#e6e6e6"

    def spans(ax, mask):
        a, b = _runs(mask)
        for i, j in zip(a, b):
            ax.axvspan(t[i], t[j - 1], color=shade, lw=0, zorder=0)

    ax = axs[0]
    spans(ax, st["in_blink"].to_numpy(bool))
    ax.plot(t, st["pupil_raw"], color="k", lw=0.5)
    ax.set_title(f"Raw samples ({hz:,.0f} per second), with the tracker\u2019s blinks shaded", fontsize=8, loc="left")
    ax = axs[1]
    spans(ax, st["blink_pad"].to_numpy(bool))
    ax.plot(t, st["pupil"], color="k", lw=0.5)
    ax.set_title(f"Blinks padded by {pad_ms:g} ms and removed", fontsize=8, loc="left")
    ax = axs[2]
    yb = np.where(okb, bt["pupil"].to_numpy(float), np.nan)
    if zoom is None:
        ax.plot(tb, yb, color="k", lw=0.7, drawstyle="steps-post")
        ax.set_title(f"{bin_ms:g} ms bins", fontsize=8, loc="left")
    else:
        from matplotlib.patches import Rectangle
        from matplotlib.ticker import MultipleLocator
        z0, z1 = float(zoom[0]), float(zoom[1])
        if not z1 > z0:
            raise ValueError("plot_trial: zoom must be (start, end) with end > start, in seconds")
        zs = [f"{v:.1f}" if abs(v * 10 - round(v * 10)) < 1e-9 else f"{v:g}" for v in (z0, z1)]
        m = (t >= z0) & (t <= z1)
        mb = (tb >= z0) & (tb < z1)
        yz = st["pupil"].to_numpy(float)[m]
        lab = "Samples (one per ms)" if round(hz) == 1000 else f"Samples ({hz:,.0f} per second)"
        ax.plot(t[m], yz, color="#9a9a9a", lw=0.6, label=lab)
        ax.hlines(yb[mb], tb[mb], tb[mb] + bin_ms / 1000, color="k", lw=1.6, label=f"{bin_ms:g} ms bin means")
        ax.set_xlim(z0, z1)
        if (z1 - z0) * 1000 / bin_ms <= 100:         # minor ticks at the bin edges
            ax.xaxis.set_minor_locator(MultipleLocator(bin_ms / 1000))
            ax.tick_params(axis="x", which="minor", length=2, width=0.5)
        if np.isfinite(yz).any():
            y0, y1 = np.nanmin(yz), np.nanmax(yz)
            r = max(y1 - y0, 1.0)
            ax.set_ylim(y0 - 0.12 * r, y1 + 0.3 * r)   # room for the legend
            hb = st["pupil_raw"].to_numpy(float)
            hb = np.nanmax(hb[np.isfinite(hb)]) if np.isfinite(hb).any() else y1
            axs[1].add_patch(Rectangle((z0, y0 - 0.05 * hb), z1 - z0, y1 - y0 + 0.1 * hb, fill=False, ec="#555555",
                                       lw=0.6, zorder=3))
            axs[1].text((z0 + z1) / 2, y0 - 0.07 * hb, "C", ha="center", va="top", fontsize=7, fontweight="bold")
        ax.legend(loc="upper right", fontsize=7, handlelength=1.6, ncol=2, borderaxespad=0.1)
        ax.set_title(f"{bin_ms:g} ms bins: {zs[0]}\u2013{zs[1]} s enlarged (box C in panel B)", fontsize=8, loc="left")
    info = samples.attrs or {}
    what = "diameter" if info.get("pupil_unit") == "diameter" else "area"
    unit = "\n(arbitrary units)" if info.get("tracker", "EyeLink") == "EyeLink" else ""
    for ax in axs[:3]:
        ax.set_ylabel(f"Pupil {what}{unit}")
    ax = axs[3]
    ax.axvspan(window[0] / 1000, window[1] / 1000, color=shade, lw=0, zorder=0)
    ax.axhline(0, color="k", lw=0.4)
    ax.plot(tb, bt["change"].to_numpy(float), color="k", lw=0.7, drawstyle="steps-post")
    ax.set_title(f"Baseline-corrected ({window[0]:g}\u2013{window[1]:g} ms baseline shaded)", fontsize=8, loc="left")
    ax.set_ylabel("Change from baseline\n(% of reader mean)")
    ax.set_xlabel("Time from text onset (s)")
    lo, hi = (xlim if xlim is not None else (0, max(t.max(), tb.max() + bin_ms / 1000)))
    ax.set_xlim(lo, hi)
    vals = st["pupil_raw"].to_numpy(float)[(t >= lo) & (t <= hi)]
    if np.isfinite(vals).any():                     # A to C (A and B with zoom) share the scale of the raw samples shown
        top = np.nanmax(vals)
        for ax in axs[:2] if zoom is not None else axs[:3]:
            ax.set_ylim(0, top * 1.05)
    cv = bt["change"].to_numpy(float)[(tb >= lo) & (tb <= hi)]
    if np.isfinite(cv).any():                       # D: the range of the change shown, with zero in view
        c0, c1 = min(np.nanmin(cv), 0.0), max(np.nanmax(cv), 0.0)
        m = 0.08 * (c1 - c0 if c1 > c0 else 1.0)
        axs[3].set_ylim(c0 - m, c1 + m)
    for ax, letter in zip(axs, "ABCD"):
        ax.text(-0.09, 1.08, letter, transform=ax.transAxes, fontsize=10, fontweight="bold", va="bottom", ha="left")
    fig.trial_data = {"samples": st, "bins": bt, "reader_mean": rm}
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
    """Grand-mean time course by version with 95% confidence intervals across readers (Figure 3B of the paper).

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
