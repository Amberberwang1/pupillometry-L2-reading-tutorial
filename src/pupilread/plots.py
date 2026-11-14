"""Stage 3.6, data quality checks and visualisation (black-and-white figures in the style of the paper)."""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ._utils import ok_mask, sampling_rate, sort_trials, window_mask

LINESTYLES = ["-", (0, (4, 2)), (0, (1, 1.5)), (0, (6, 2, 1, 2))]


def _plt():
    import matplotlib
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
                         "axes.linewidth": 0.6})
    return matplotlib, plt


def _levels(df, by):
    return [] if by is None or by not in df.columns else sorted(df[by].dropna().unique(), key=str)


def find_spikes(bins: pd.DataFrame, min_drop: float = 20, shoulders: Tuple[float, float] = (60, 200),
                column: str = "pupil") -> pd.DataFrame:
    """Residual spikes left after blink removal (stage 3.6).

    A valid bin is part of a spike when its pupil size, as a percentage of the reader mean, lies more than ``min_drop``
    points below the lower of two shoulders: the median of the valid bins ``shoulders[0]`` to ``shoulders[1]`` ms before
    it and the median of those after it (one shoulder suffices next to a gap). Slow changes and steps leave one shoulder
    close to the bin; only a drop that recovers within about 200 ms clears both. Returns one row per bin of ``bins``
    (same index) with ``drop`` (points below the shoulders) and ``spike`` (True or False). The rule of thumb is that no
    more than about 5% of trials should contain a spike (Mathôt & Vilotijević, 2023); see ``spike_rate()``.
    """
    import warnings
    from numpy.lib.stride_tricks import sliding_window_view
    from .baseline import reader_means
    bin_ms = float((bins.attrs or {}).get("bin_ms", 20))
    k0, k1 = int(round(shoulders[0] / bin_ms)), int(round(shoulders[1] / bin_ms))
    ok = np.asarray(ok_mask(bins), bool)
    means = reader_means(bins, column)
    pct = 100 * bins[column].to_numpy(float) / bins["reader"].map(means).to_numpy(float)
    drop = np.full(len(bins), np.nan)
    pos = np.rint(bins["time"].to_numpy(float) / bin_ms).astype(np.int64)
    for _, idx in bins.groupby(["reader", "trial"], sort=False).indices.items():
        idx = idx[ok[idx]]
        if len(idx) < 2:
            continue
        p = pos[idx] - pos[idx].min()
        dense = np.full(p.max() + 1 + 2 * k1, np.nan)
        dense[p + k1] = pct[idx]
        win = sliding_window_view(dense, 2 * k1 + 1)[p]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            left = np.nanmedian(win[:, :k1 - k0 + 1], axis=1)
            right = np.nanmedian(win[:, k1 + k0:], axis=1)
        ref = np.where(np.isnan(left), right, np.where(np.isnan(right), left, np.minimum(left, right)))
        drop[idx] = ref - pct[idx]
    out = pd.DataFrame({"drop": drop}, index=bins.index)
    out["spike"] = out["drop"] > min_drop
    return out


def spike_rate(bins: pd.DataFrame, spikes: Optional[pd.DataFrame] = None, by: Optional[str] = "version", **kw) -> pd.DataFrame:
    """Share of trials with at least one residual spike (%), overall and per level of ``by`` (stage 3.6)."""
    sp = find_spikes(bins, **kw) if spikes is None else spikes
    cols = ["reader", "trial"] + ([by] if by and by in bins.columns else [])
    per = bins[cols].join(sp["spike"]).groupby(cols)["spike"].any().reset_index()
    rows = [{"level": "all", "trials": len(per), "pct_with_spike": 100 * per["spike"].mean()}]
    if len(cols) == 3:
        for lv, g in per.groupby(by):
            rows.append({"level": lv, "trials": len(g), "pct_with_spike": 100 * g["spike"].mean()})
    return pd.DataFrame(rows)


def plot_overlays(bins: pd.DataFrame, column: str = "change", by: Optional[str] = "version", readers: Optional[Sequence] = None,
                  max_readers: int = 6, ncols: int = 3, mark_spikes: bool = True):
    """Trial-level overlays: every trial's trace, one panel per reader, line style by ``by`` (stage 3.6).

    Overlays reveal residual artifacts that a summary statistic hides, such as spikes, gaps or implausible trajectories.
    With ``mark_spikes=True`` (default), a triangle marks each spike found by ``find_spikes()``, each panel title gives
    the share of that reader's trials with a spike, and ``fig.spike_rate`` holds the share over all trials in ``bins``
    (rule of thumb: no more than about 5%).
    """
    _, plt = _plt()
    rd = list(readers) if readers is not None else list(pd.unique(bins["reader"]))[:max_readers]
    nrows = int(np.ceil(len(rd) / ncols))
    fig, axs = plt.subplots(nrows, ncols, figsize=(2.4 * ncols, 1.8 * nrows), squeeze=False, sharex=True)
    lv = _levels(bins, by)
    ok = ok_mask(bins)
    sp = find_spikes(bins) if mark_spikes and "pupil" in bins.columns else None
    for ax, r in zip(axs.ravel(), rd):
        sel = ok & (bins["reader"] == r)
        b = bins[sel]
        for (_, tr), g in b.groupby(["reader", "trial"]):
            g = g.sort_values("time")
            y = g[column].to_numpy(float)
            gap = np.r_[False, np.diff(g["time"].to_numpy(float)) > 1.5 * float((bins.attrs or {}).get("bin_ms", 20))]
            ls = LINESTYLES[lv.index(g[by].iat[0]) % 4] if lv else "-"
            ax.plot(g["time"] / 1000, np.where(gap, np.nan, y), color="k", lw=0.4, alpha=0.6, ls=ls)
        title = f"Reader {r}"
        if sp is not None:
            s = b.join(sp["spike"])
            ev = s[s["spike"]].sort_values(["trial", "time"])
            first = (ev.groupby("trial")["time"].diff().fillna(np.inf) > 100).to_numpy()
            ev = ev[first]
            ax.scatter(ev["time"] / 1000, ev[column] - 4, marker="^", s=8, color="k", lw=0, zorder=5)
            n_tr = b["trial"].nunique()
            title += f": spikes in {100 * s.groupby('trial')['spike'].any().mean():.0f}% of {n_tr} trials"
        ax.set_title(title, fontsize=7, loc="left")
        ax.axhline(0, color="k", lw=0.3)
    for ax in axs.ravel()[len(rd):]:
        ax.set_visible(False)
    for ax in axs[-1]:
        ax.set_xlabel("Time from text onset (s)")
    for ax in axs[:, 0]:
        ax.set_ylabel("Pupil change\n(% of reader mean)" if column == "change" else column)
    fig.tight_layout()
    if sp is not None:
        fig.spikes = sp
        fig.spike_rate = spike_rate(bins, sp, by=by)
    return fig


def _runs(mask):
    """Start and end (exclusive) indices of every run of True in ``mask``."""
    d = np.diff(np.r_[0, np.asarray(mask, bool).astype(np.int8), 0])
    return np.flatnonzero(d == 1), np.flatnonzero(d == -1)


def plot_trial(samples: pd.DataFrame, trial, reader=None, pad_ms: float = 100, bin_ms: float = 20,
               window: Tuple[float, float] = (0, 200), pupil_range: Tuple[float, float] = (100, 10000),
               min_valid: float = 0.5, reader_mean: Optional[float] = None,
               xlim: Optional[Tuple[float, float]] = None, zoom: Optional[Tuple[float, float]] = None):
    """One trial at four stages of the pipeline, in the order of processing (stages 3.1 to 3.3; Figure 2 of the paper).

    (A) The raw samples, with the blinks the tracker marked shaded. (B) The samples after each blink is padded by
    ``pad_ms`` and the padded and invalid samples are removed (:func:`pad_blinks`), with the padded stretches shaded.
    (C) The ``bin_ms`` bins (:func:`bin`). (D) The bins after subtractive baseline correction over ``window``, as a
    percentage of the reader mean (:func:`baseline`), with the baseline window shaded. With ``zoom``, a fifth panel
    (E) enlarges a short stretch, boxed in panel C, and draws the samples of B (grey line) with their bin means
    (black bars). The panels run the package's own functions, so they show exactly what the pipeline does to the
    trial.

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
        A short stretch in seconds, such as (3.0, 3.5), for a close-up panel (E). Over a whole trial, the samples and
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
        s = s.drop(columns=[c for c in ("pupil", "invalid", "blink_pad", "speed_artifact", "valid") if c in s.columns])
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
    if zoom is not None:
        z0, z1 = float(zoom[0]), float(zoom[1])
        if not z1 > z0:
            raise ValueError("plot_trial: zoom must be (start, end) with end > start, in seconds")
    fig = plt.figure(figsize=(6.6, 6.4 if zoom is None else 8.4))
    if zoom is None:
        gs = fig.add_gridspec(4, 1, hspace=0.45)
    else:                                           # the steps A to D, then a wider gap before the close-up E
        outer = fig.add_gridspec(2, 1, height_ratios=[4, 1], hspace=0.3)
        gs = outer[0].subgridspec(4, 1, hspace=0.45)
    axs = [fig.add_subplot(gs[0])]
    for i in (1, 2, 3):                             # A to D: the processing steps, on one time axis
        axs.append(fig.add_subplot(gs[i], sharex=axs[0]))
    for ax in axs[:3]:
        ax.tick_params(labelbottom=False)
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
    ax.set_title(f"Step 1: blinks padded by {pad_ms:g} ms and removed (Section 3.2)", fontsize=8, loc="left")
    ax = axs[2]
    yb = np.where(okb, bt["pupil"].to_numpy(float), np.nan)
    ax.plot(tb, yb, color="k", lw=0.7, drawstyle="steps-post")
    ax.set_title(f"Step 2: {bin_ms:g} ms bins (Section 3.1)", fontsize=8, loc="left")
    info = samples.attrs or {}
    what = "diameter" if info.get("pupil_unit") == "diameter" else "area"
    unit = "\n(arbitrary units)" if info.get("tracker", "EyeLink") == "EyeLink" else ""
    for ax in axs[:3]:
        ax.set_ylabel(f"Pupil {what}{unit}")
    ax = axs[3]
    ax.axvspan(window[0] / 1000, window[1] / 1000, color=shade, lw=0, zorder=0)
    ax.axhline(0, color="k", lw=0.4)
    ax.plot(tb, bt["change"].to_numpy(float), color="k", lw=0.7, drawstyle="steps-post")
    ax.set_title(f"Step 3: baseline-corrected, {window[0]:g}\u2013{window[1]:g} ms baseline shaded (Section 3.3)",
                 fontsize=8, loc="left")
    ax.set_ylabel("Change from baseline\n(% of reader mean)")
    ax.set_xlabel("Time from text onset (s)")
    lo, hi = (xlim if xlim is not None else (0, max(t.max(), tb.max() + bin_ms / 1000)))
    ax.set_xlim(lo, hi)
    vals = st["pupil_raw"].to_numpy(float)[(t >= lo) & (t <= hi)]
    top = np.nanmax(vals) if np.isfinite(vals).any() else None
    if top is not None:                             # A to C share the scale of the raw samples shown
        for ax in axs[:3]:
            ax.set_ylim(0, top * 1.05)
    cv = bt["change"].to_numpy(float)[(tb >= lo) & (tb <= hi)]
    if np.isfinite(cv).any():                       # D: the range of the change shown, with zero in view
        c0, c1 = min(np.nanmin(cv), 0.0), max(np.nanmax(cv), 0.0)
        m = 0.08 * (c1 - c0 if c1 > c0 else 1.0)
        axs[3].set_ylim(c0 - m, c1 + m)
    if zoom is not None:                            # E: a close-up of panel C, samples against their bin means
        from matplotlib.patches import Rectangle
        from matplotlib.ticker import MultipleLocator
        zs = [f"{v:.1f}" if abs(v * 10 - round(v * 10)) < 1e-9 else f"{v:g}" for v in (z0, z1)]
        ax = fig.add_subplot(outer[1])
        axs.append(ax)
        m = (t >= z0) & (t <= z1)
        mb = (tb >= z0) & (tb < z1)
        yz = st["pupil"].to_numpy(float)[m]
        lab = "Samples of B (one per ms)" if round(hz) == 1000 else f"Samples of B ({hz:,.0f} per second)"
        ax.plot(t[m], yz, color="#9a9a9a", lw=0.6, label=lab)
        ax.hlines(yb[mb], tb[mb], tb[mb] + bin_ms / 1000, color="k", lw=1.6, label=f"{bin_ms:g} ms bin means of C")
        ax.set_xlim(z0, z1)
        if (z1 - z0) * 1000 / bin_ms <= 100:         # minor ticks at the bin edges
            ax.xaxis.set_minor_locator(MultipleLocator(bin_ms / 1000))
            ax.tick_params(axis="x", which="minor", length=2, width=0.5)
        if np.isfinite(yz).any():
            y0, y1 = np.nanmin(yz), np.nanmax(yz)
            r = max(y1 - y0, 1.0)
            ax.set_ylim(y0 - 0.12 * r, y1 + 0.3 * r)   # room for the legend
            hb = top if top is not None else y1
            axs[2].add_patch(Rectangle((z0, y0 - 0.05 * hb), z1 - z0, y1 - y0 + 0.1 * hb, fill=False, ec="#555555",
                                       lw=0.6, zorder=3))
            axs[2].text((z0 + z1) / 2, y0 - 0.07 * hb, "E", ha="center", va="top", fontsize=7, fontweight="bold")
        ax.legend(loc="upper right", fontsize=7, handlelength=1.6, ncol=2, borderaxespad=0.1)
        ax.set_title(f"Close-up of {zs[0]}\u2013{zs[1]} s (box E in panel C)", fontsize=8, loc="left")
        ax.set_ylabel(f"Pupil {what}{unit}")
        ax.set_xlabel("Time from text onset (s)")
    for ax, letter in zip(axs, "ABCDE"):
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


def plot_quality(trials: pd.DataFrame, by: str = "version", min_valid: float = 0.5, step: float = 5,
                 measures: Sequence[str] = ()):
    """Data lost per trial, one histogram per version, with the exclusion threshold as a dashed line (stage 3.6).

    ``trials`` is the per-trial table of ``data_loss()``. Look for one histogram lying further to the right, or with more
    trials past the threshold (``1 - min_valid``): that version lost more data. ``measures`` adds panels of reader means
    joined across versions for other columns, such as ``"blink_rate"`` or ``"saccade_rate"``.
    """
    _, plt = _plt()
    ms = [m for m in measures if m in trials.columns]
    fig, axs = plt.subplots(1, 1 + len(ms), figsize=(2.6 + 1.6 * len(ms), 2.2), squeeze=False)
    lv = _levels(trials, by)
    ax = axs[0, 0]
    lost = 100 - trials["pct_valid"].to_numpy(float)
    edges = np.arange(0, 100 + step, step)
    styles = [dict(histtype="stepfilled", color="#cfcfcf", lw=0), dict(histtype="step", color="k", lw=1.0),
              dict(histtype="step", color="k", lw=1.0, ls=(0, (3, 2))), dict(histtype="step", color="#777777", lw=1.0)]
    for i, level in enumerate(lv or [None]):
        x = lost if level is None else lost[(trials[by] == level).to_numpy()]
        ax.hist(x, bins=edges, label=None if level is None else str(level), **styles[i % 4])
    thr = 100 * (1 - min_valid)
    ax.axvline(thr, color="k", lw=0.8, ls=(0, (3, 2)))
    ax.text(thr + 2, ax.get_ylim()[1] * 0.95, f"excluded\n(> {thr:g}% lost)", fontsize=6.5, va="top")
    ax.set_xlim(0, 100)
    ax.set_xlabel("Data lost per trial (%)")
    ax.set_ylabel("Trials")
    if lv:
        ax.legend(fontsize=6.5, loc="upper right", bbox_to_anchor=(1.0, 0.72))
    for ax, m in zip(axs[0, 1:], ms):
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
              baseline_window=(0, 200), cut_before_keypress_ms: float = 3000, section_px: float = 100):
    """Gaze checks (stage 3.6, Figure 7C).

    Left panel: mean gaze position by version. Small symbols are reader means of horizontal and vertical gaze in the
    analysis window, optionally relative to the gaze position in the baseline window; large symbols are the version
    means. Large symbols far apart mean readers looked at different parts of the screen in the two versions; then apply
    ``correct_gaze()`` and report the result with and without it (Section 3.4).

    Right panel (when ``bins`` holds ``pupil_corrected``, i.e. after ``correct_gaze()``): mean pupil size, in % of the
    reader mean, in ``section_px`` sections of horizontal gaze, before and after the correction. Before correction the
    line falls from left to right (the pupil looks smaller away from the camera); a correction that works makes it
    flatter. ``fig.gaze_slope`` holds the two lines.
    """
    from .baseline import reader_means
    _, plt = _plt()
    ok = ok_mask(bins)
    b = bins[ok].copy()
    key = ["reader", "trial"]
    cut = cut_before_keypress_ms if "duration" in b.columns else 0
    inwin = window_mask(b, window, cut, "plot_gaze")
    w = b[inwin].groupby(key)[["gaze_x", "gaze_y"]].mean()
    if relative_to_baseline:
        bb = b[(b["time"] >= baseline_window[0]) & (b["time"] < baseline_window[1])].groupby(key)[["gaze_x", "gaze_y"]].mean()
        w = w - bb
    info = bins.drop_duplicates(key).set_index(key)[[by]]
    w = w.join(info).reset_index()
    pr = w.groupby(["reader", by])[["gaze_x", "gaze_y"]].mean().reset_index()
    two = "pupil_corrected" in b.columns
    fig, axs = plt.subplots(1, 2 if two else 1, figsize=(6.0 if two else 3.0, 2.6), squeeze=False)
    ax = axs[0, 0]
    lv = _levels(pr, by)
    marks = ["s", "o", "^", "D"]
    for i, level in enumerate(lv):
        z = pr[pr[by] == level]
        ax.scatter(z["gaze_x"], z["gaze_y"], s=8, facecolor="k" if i == 1 else "none", edgecolor="#8a8a8a",
                   marker=marks[i % 4], lw=0.5, alpha=0.8)
    for i, level in enumerate(lv):
        z = pr[pr[by] == level]
        ax.scatter([z["gaze_x"].mean()], [z["gaze_y"].mean()], s=60, facecolor="k" if i == 1 else "white", edgecolor="k",
                   marker=marks[i % 4], lw=1.0, zorder=5, label=f"{level} (mean)")
    ax.invert_yaxis()
    ax.set_xlabel("Horizontal gaze" + (" relative to baseline" if relative_to_baseline else "") + " (px)")
    ax.set_ylabel("Vertical gaze (px)")
    ax.legend(fontsize=7)
    fig.gaze_table = pr
    if two:
        ax = axs[0, 1]
        m = reader_means(bins)
        g = b[np.isfinite(b["gaze_x"].to_numpy(float))].copy()
        g["section"] = (g["gaze_x"] // section_px) * section_px + section_px / 2
        rows = {}
        for col, lab in (("pupil", "Before correction"), ("pupil_corrected", "After correction")):
            g["_p"] = 100 * g[col] / g["reader"].map(m)
            t = g.groupby(["reader", "section"])["_p"].mean().unstack("section")
            t = t.sub(t.mean(axis=1), axis=0)              # each reader's own level removed
            rows[lab] = t.mean()
        sl = pd.DataFrame(rows)
        n = g.groupby("section").size()
        sl = sl[n.reindex(sl.index).fillna(0) >= 0.005 * n.sum()]   # drop sparse sections at the screen edges
        ax.plot(sl.index, sl["Before correction"], color="k", lw=1.0, ls=(0, (3, 2)), label="Before correction")
        ax.plot(sl.index, sl["After correction"], color="k", lw=1.4, label="After correction")
        ax.axhline(0, color="#9a9a9a", lw=0.5)
        ax.set_xlabel("Horizontal gaze (px)")
        ax.set_ylabel("Pupil size\n(% of reader mean, centred)")
        ax.legend(fontsize=7)
        fig.gaze_slope = sl
    fig.tight_layout()
    return fig
