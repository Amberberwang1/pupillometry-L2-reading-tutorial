"""Section 5, what the decisions change: the trial measure under each option, one column per option.

Each option changes one decision of the primary estimate (a reduced form of the multiverse analysis of Steegen et al.,
2016). :func:`options_table` returns one row per trial and one column per option, with missing values for the trials
an option leaves out, plus standardised trial-level covariates; ``attrs["options"]`` (and :func:`options_spec`) give
the model for each column, which ``multiverse.R`` fits with lme4.
"""
from __future__ import annotations

import warnings
from typing import Mapping, Optional

import numpy as np
import pandas as pd

from ._utils import TRIAL_KEY
from .baseline import baseline, low_baselines, reader_means
from .controls import add_covariates, control_predictors
from .gaze import correct_gaze, regression_slopes, saccade_steps, step_slopes
from .io import to_diameter
from .levels import fixation_means
from .windows import trial_means

#: Control predictors of the paper (see :func:`add_covariates`): time, gaze position and eccentricity, fixation
#: duration and distance to the next fixation. Local text density (``ink_fovea``, ``ink_parafovea``, computed from the
#: text layout) is added when the bins carry those columns (:data:`OPTIONAL_CONTROLS`).
CONTROLS = ("time_s", "time2", "gaze_x", "gaze_y", "eccentricity", "fix_duration", "next_distance")
OPTIONAL_CONTROLS = ("ink_fovea", "ink_parafovea")

#: The options of Table 3 and Table S2 of the paper (trial-level models; the time-course options are fitted by
#: ``gamm.R``). The geometric model needs a measured layout (``gaze.layout`` in the config) and is left out without
#: one. Keys are the output column names. Settings: ``baseline`` (arguments of :func:`baseline`), ``window`` and
#: ``cut_before_keypress_ms`` (:func:`trial_means`), ``interpolated``, ``diameter``, ``level="fixations"``, ``gaze``
#: (``method`` "regression" with ``time_terms``, "steps" with ``by`` and ``slopes`` = "joint", "by_type" or "map", or
#: "geometric" with ``layout``, by default the ``gaze.layout`` setting of the config),
#: ``controls`` (and ``optional_controls``, used when present), ``min_baseline_pct``, ``min_valid_trial``, ``subset``,
#: ``samples`` (sample-level settings, e.g. ``{"blinks": {"pad_ms": 50}}``), and the model: ``random`` ("slope" or
#: "intercepts"), ``covariates`` and ``term``.
PAPER_OPTIONS = {
    "change_0_20s": dict(label="Primary estimate", section="3", table="3"),
    "fixations": dict(label="Fixation averages", level="fixations", section="3.1", table="3"),
    "valid_75": dict(label="At least 75% valid samples", min_valid_trial=0.75, section="3.2", table="3"),
    "baseline_0_500": dict(label="0-500 ms baseline", baseline=dict(window=(0, 500)), section="3.3", table="3"),
    "low_baselines_kept": dict(label="Low baselines kept", min_baseline_pct=None, section="3.3", table="3"),
    "no_baseline": dict(label="No baseline correction", baseline=dict(method="none"), section="3.3", table="3"),
    "baseline_covariate": dict(label="Baseline as covariate", baseline=dict(method="none"), covariates=["baseline_z"],
                               section="3.3", table="3"),
    "diameter": dict(label="Diameter scale", diameter=True, section="3.3", table="3"),
    "whole_trial": dict(label="Whole trial", window=(500, None), section="3.5", table="3"),
    "random_intercepts": dict(label="Random intercepts only", random="intercepts", section="3.7", table="3"),
    "control_predictors": dict(label="Control predictors", controls=list(CONTROLS),
                               optional_controls=list(OPTIONAL_CONTROLS), section="3.7", table="3"),
    "gaze_regression": dict(label="Regression slopes", gaze=dict(method="regression"), section="3.4", table="3"),
    "gaze_steps_eye": dict(label="Saccade steps, slopes per eye", gaze=dict(method="steps", by="eye"), section="3.4",
                           table="3"),
    "gaze_steps_type": dict(label="Saccade steps, slopes by saccade type (exploratory)",
                            gaze=dict(method="steps", by="eye", slopes="by_type"), section="3.4", table="3"),
    "gaze_geometric": dict(label="Geometric model, measured layout", gaze=dict(method="geometric"), section="3.4",
                           table="3"),
    "fixations_same_trials": dict(label="Samples, same trials as fixation averages", subset="fixations", section="3.1",
                                  table="S2"),
    "window_2_20": dict(label="Window 2-20 s", window=(2000, 20000), section="3.3", table="S2"),
    "window_3_20": dict(label="Window 3-20 s", window=(3000, 20000), section="3.3", table="S2"),
    "window_5_20": dict(label="Window 5-20 s", window=(5000, 20000), section="3.3", table="S2"),
    "left_eye": dict(label="Left-eye readers", subset={"eye": "left"}, section="3.4", table="S2"),
    "right_eye": dict(label="Right-eye readers", subset={"eye": "right"}, section="3.4", table="S2"),
    "whole_trial_covariates": dict(label="Whole trial + duration, blink and saccade rates", window=(500, None),
                                   covariates=["duration_z", "blink_z", "saccade_z"], section="3.5", table="S2"),
    "cut_1s": dict(label="Last 1 s before the key press removed", cut_before_keypress_ms=1000, section="3.5",
                   table="S2"),
    "cut_2s": dict(label="Last 2 s before the key press removed", cut_before_keypress_ms=2000, section="3.5",
                   table="S2"),
    "gaze_regression_time": dict(label="Regression slopes with time", gaze=dict(method="regression", time_terms=True),
                                 section="3.4", table="S2"),
    "gaze_steps_reader": dict(label="Saccade steps, slopes per reader", gaze=dict(method="steps", by="reader"),
                              section="3.4", table="S2"),
    "gaze_steps_map": dict(label="Saccade steps, horizontal map (exploratory)",
                           gaze=dict(method="steps", by="eye", slopes="map"), section="3.4", table="S2"),
    "interpolated": dict(label="Blinks interpolated", interpolated=True, section="3.2", table="S2"),
    "baseline_denominator": dict(label="Reader-baseline denominator", baseline=dict(scale="baseline_mean"),
                                 section="3.3", table="S2"),
    "version_x_eye": dict(label="Version x eye interaction (left minus right)", covariates=["eye_c", "contrast:eye_c"],
                          term="contrast:eye_c", section="3.4", table="S2"),
}

_MODEL_KEYS = ("label", "section", "table", "random", "covariates", "term")


def options_spec(options: Optional[Mapping] = None) -> pd.DataFrame:
    """One row per option: output column, label, model (random part, covariates, tested term), section and table.

    This is the table that ``multiverse.R`` reads (``options.csv``) to fit one model per option column.
    """
    options = PAPER_OPTIONS if options is None else options
    rows = []
    for name, o in options.items():
        rows.append({"column": name, "label": o.get("label", name), "random": o.get("random", "slope"),
                     "covariates": " + ".join(o.get("covariates", [])), "term": o.get("term", "contrast"),
                     "section": o.get("section", ""), "table": o.get("table", "")})
    return pd.DataFrame(rows)


def _z(v: pd.Series, ref: Optional[pd.Series] = None) -> pd.Series:
    r = v if ref is None else ref
    return (v - r.mean()) / r.std(ddof=1)


class _Context:
    """Shared intermediate results (reader means, saccade steps) for the options of one table."""

    def __init__(self, data, base_window, window, min_pct, steps, display=None, layout=None):
        self.data = data
        self.display = dict(display or {})
        self.layout = layout
        self.bins = data.bins
        self.means = reader_means(self.bins)
        self.base_window = tuple(base_window)
        self.window = tuple(window)
        self.min_pct = min_pct
        self._steps = steps
        self._fix = None

    @property
    def fixations(self):
        if self._fix is None:
            f = getattr(self.data, "fixations", None)
            if f is None:
                raise ValueError("options_table: this option needs fixations (pass fixations=...)")
            k = self.bins.drop_duplicates(TRIAL_KEY)[TRIAL_KEY].astype(str)
            ff = f.copy()
            m = pd.MultiIndex.from_arrays([ff["reader"].astype(str), ff["trial"].astype(str)]).isin(pd.MultiIndex.from_frame(k))
            self._fix = ff[m].reset_index(drop=True)
        return self._fix

    @property
    def has_fixations(self):
        return getattr(self.data, "fixations", None) is not None

    @property
    def steps(self):
        if self._steps is None:
            self._steps = saccade_steps(self.bins, self.fixations, means=self.means)
        return self._steps

    def bins_for(self, name, o):
        if o.get("samples"):
            ob = getattr(self.data, "option_bins", {}) or {}
            if name not in ob:
                raise ValueError(f"options_table: option {name!r} changes sample-level settings; pass the sample table, "
                                 "or list the option in run_pipeline's config so that its bins are prepared per reader")
            return ob[name]
        return self.bins


def _measure(ctx: _Context, name: str, o: Mapping) -> pd.Series:
    """The trial measure of one option for every trial (before the option's subset is applied)."""
    bins = ctx.bins_for(name, o)
    means = ctx.means if bins is ctx.bins else reader_means(bins)
    window = tuple(o.get("window", ctx.window))
    bkw = dict(window=ctx.base_window, method="subtractive", scale="reader_mean")
    bkw.update(o.get("baseline", {}))
    if o.get("level") == "fixations":
        bw = tuple(bkw["window"])
        v = fixation_means(ctx.fixations, means, window=window, baseline=bw, name=name)
        return v.set_index(TRIAL_KEY)[name]
    column = None
    if o.get("diameter"):
        bins = to_diameter(bins)
        means = reader_means(bins)
    g = o.get("gaze")
    if g:
        method = g.get("method")
        if method == "regression":
            sl = regression_slopes(bins, window=ctx.base_window, min_baseline_pct=ctx.min_pct or 0,
                                   time_terms=g.get("time_terms", False), means=means)
            bins = correct_gaze(bins, sl, method="regression")
        elif method == "steps":
            by = g.get("by", "eye")
            sl = step_slopes(ctx.steps, by=by, method=g.get("slopes", "joint"))
            bins = correct_gaze(bins, sl, method="steps", by=by, means=means)
        elif method == "geometric":
            layout = g.get("layout", ctx.layout)
            if layout is None:
                raise ValueError(f"option {name!r} needs a measured layout (gaze.layout in the config)")
            bins = correct_gaze(bins, method="geometric", layout=layout)
            means = reader_means(bins, column="pupil_corrected")
        else:
            raise ValueError(f"options_table: unknown gaze method {method!r} in option {name!r}")
        column = "pupil_corrected"
    if o.get("interpolated"):
        if "pupil_interp" not in bins.columns:
            raise ValueError("options_table: the 'interpolated' option needs pupil_interp in the bins (run interpolate())")
        column = "pupil_interp"
    b = baseline(bins, column=column, means=means, **bkw)
    if o.get("controls"):
        if any(c not in b.columns for c in o["controls"]):
            d = ctx.display
            b = add_covariates(b, fixations=ctx.fixations if ctx.has_fixations else None,
                               center=(d.get("width", 1024) / 2, d.get("height", 768) / 2),
                               px_per_degree=d.get("px_per_degree"))
        cov = [c for c in o["controls"] if c in b.columns] + [c for c in o.get("optional_controls", []) if c in b.columns]
        missing = [c for c in o["controls"] if c not in b.columns]
        if missing:
            warnings.warn(f"options_table: option {name!r} leaves out control predictors missing from the bins: {missing}")
        if not cov:
            raise ValueError(f"options_table: option {name!r} has no control predictors in the bins (see add_covariates)")
        adj, _ = control_predictors(b, cov, window=window, min_baseline_pct=ctx.min_pct, name=name,
                                    complete_cases=o.get("complete_cases"))
        return adj.set_index(TRIAL_KEY)[name]
    t = trial_means(b, window=window, cut_before_keypress_ms=o.get("cut_before_keypress_ms", 0), name=name)
    return t.set_index(TRIAL_KEY)[name]


def _aligned(v: pd.Series, key: pd.MultiIndex) -> np.ndarray:
    """Values of a (reader, trial)-indexed series in the order of ``key`` (missing where absent)."""
    idx = pd.MultiIndex.from_arrays([v.index.get_level_values(0).astype(str), v.index.get_level_values(1).astype(str)])
    return pd.Series(v.to_numpy(float), index=idx).reindex(key).to_numpy(float)


def options_table(samples, options: Optional[Mapping] = None, fixations: Optional[pd.DataFrame] = None,
                  config=None, steps: Optional[pd.DataFrame] = None, trials: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """The trial measure under each option, one column per option, for the R multiverse script (Section 5).

    Parameters
    ----------
    samples : DataFrame or PupilData
        The sample table of one or more readers (:func:`read_eyelink`), which is prepared with the settings of
        ``config`` (:func:`prepare`), or data already prepared by :func:`prepare` or :func:`run_pipeline`.
    options : dict, optional
        Option name (the output column) -> settings, as in :data:`PAPER_OPTIONS` (the default: the options of Tables 3
        and S2). Each option changes one decision of the primary estimate; settings not named keep the primary choice.
        The geometric gaze correction is left out unless the config (``gaze.layout``) or the option gives a layout.
    fixations : DataFrame, optional
        Fixation table (:func:`read_fixations`), for the fixation-level and step-based options.
    config : dict or str, optional
        Pipeline settings (see :func:`run_pipeline`); the primary baseline window, analysis window and low-baseline
        cut-off are taken from it.
    steps : DataFrame, optional
        Saccade steps (:func:`saccade_steps`), if already computed.
    trials : DataFrame, optional
        Trial table with pct_valid, duration_s, blink_rate and saccade_rate (``data_loss().trials``), if not part of
        the prepared data.

    Returns
    -------
    DataFrame
        One row per trial with a baseline: reader, item, trial, version, eye, baseline_pct, pct_valid, duration_s,
        blink_rate, saccade_rate, the standardised covariates duration_z, blink_z, saccade_z (over all trials),
        baseline_z (over the analysed trials) and eye_c (left +0.5, right -0.5), and one column per option with the
        trial measure under that option (missing for the trials it leaves out). Analysed trials have a primary
        baseline of at least ``min_pct`` of the reader mean (60%), for every option except ``low_baselines_kept``.
        ``attrs["options"]`` holds :func:`options_spec`.
    """
    from .pipeline import PupilData, load_config, prepare

    cfg = load_config(config)
    options = PAPER_OPTIONS if options is None else dict(options)
    if isinstance(samples, PupilData):
        data = samples
        if fixations is not None:
            data.fixations = fixations
    else:
        data = prepare(samples, fixations=fixations, config=cfg, options=options)
    if trials is not None:
        data.trials = trials
    base_window = tuple(cfg["baseline"]["window"])
    window = tuple(cfg["trial_means"]["window"])
    min_pct = cfg["low_baselines"]["min_pct"]
    ctx = _Context(data, base_window, window, min_pct, steps, display=cfg.get("display"),
                   layout=(cfg.get("gaze") or {}).get("layout"))
    b0 = baseline(ctx.bins, window=base_window, means=ctx.means)
    T = low_baselines(b0, min_pct=min_pct if min_pct is not None else -np.inf)
    T = T[np.isfinite(T["baseline_pct"])].drop(columns=["low", "reason"]).reset_index(drop=True)
    loss = getattr(data, "trials", None)
    if loss is not None and len(loss):
        info = [c for c in ("pct_valid", "duration_s", "blink_rate", "saccade_rate") if c in loss.columns]
        L = loss[TRIAL_KEY + info].copy()
        for c in TRIAL_KEY:
            L[c] = L[c].astype(str)
        T = T.assign(_r=T["reader"].astype(str), _t=T["trial"].astype(str)).merge(
            L.rename(columns={"reader": "_r", "trial": "_t"}), on=["_r", "_t"], how="left").drop(columns=["_r", "_t"])
    analysed = T["baseline_pct"] >= (min_pct if min_pct is not None else -np.inf)
    for c, zc in (("duration_s", "duration_z"), ("blink_rate", "blink_z"), ("saccade_rate", "saccade_z")):
        if c in T.columns:
            T[zc] = _z(T[c])
    T["baseline_z"] = _z(T["baseline_pct"], T.loc[analysed, "baseline_pct"])
    T["eye_c"] = np.where(T["eye"].astype(str).str.lower() == "left", 0.5, -0.5)
    key = pd.MultiIndex.from_arrays([T["reader"].astype(str), T["trial"].astype(str)])
    values = {}
    for name, o in options.items():
        g = o.get("gaze") or {}
        if g.get("method") == "geometric" and g.get("layout", ctx.layout) is None:
            continue                                   # no measured layout: the geometric option is left out
        try:
            values[name] = _aligned(_measure(ctx, name, o), key)
        except ValueError as e:
            warnings.warn(f"options_table: option {name!r} skipped: {e}")
    primary = values["change_0_20s"] if "change_0_20s" in values else _aligned(_measure(ctx, "change_0_20s", {}), key)
    fix_ok = np.isfinite(values["fixations"]) if "fixations" in values else None
    for name, o in options.items():
        if name not in values:
            continue
        v = values[name]
        keep = np.ones(len(T), bool)
        mp = o.get("min_baseline_pct", min_pct)
        if mp is not None:
            keep &= (T["baseline_pct"] >= mp).to_numpy()
        if o.get("min_valid_trial") is not None:
            if "pct_valid" not in T.columns:
                raise ValueError("options_table: min_valid_trial needs pct_valid (pass trials=data_loss(...).trials)")
            keep &= (T["pct_valid"] >= 100 * o["min_valid_trial"]).to_numpy()
        sub = o.get("subset")
        if sub == "fixations" or o.get("level") == "fixations":
            if fix_ok is None:
                raise ValueError("options_table: subset 'fixations' needs the 'fixations' option")
            keep &= fix_ok & np.isfinite(primary)
        elif isinstance(sub, Mapping):
            for c, val in sub.items():
                keep &= (T[c].astype(str).str.lower() == str(val).lower()).to_numpy()
        T[name] = np.where(keep, v, np.nan)
    spec = options_spec({k: v for k, v in options.items() if k in T.columns})
    T.attrs = {"options": spec.to_dict("records"), "min_pct": min_pct, "baseline_window": base_window,
               "window": window}
    return T
