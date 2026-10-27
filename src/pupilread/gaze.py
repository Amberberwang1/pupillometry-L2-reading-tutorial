"""Stage 3.4, gaze-position correction: pupil steps across saccades, artifact slopes and their removal.

Gaze-position (pupil-foreshortening) artifacts change measured pupil size immediately, whereas real pupil responses start
no earlier than about 220 ms after their cause (Mathot et al., 2018). The step in pupil size across each saccade, from
just before saccade onset to 20-120 ms after landing, therefore estimates the artifact; regressing the steps on the
saccade's horizontal and vertical size gives the artifact per pixel of gaze shift (Python 4 of the paper).

The geometric model of Hayes and Petrov (2016) instead predicts the artifact from the measured positions of eye, camera
and screen (:func:`read_layout`, :func:`foreshortening`), with no parameter estimated from the pupil data. An
exploratory hybrid scales the model to the saccade steps (:func:`geometric_scale`): the shape of the artifact comes from
the geometry, its size from the readers' own data.
"""
from __future__ import annotations

import math
import warnings
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from ._utils import check_columns, copy_attrs, ok_mask, warn_order
from .baseline import reader_means as _reader_means
from .levels import retained_fixations

SACCADE_TYPES = ("forward", "regression", "return sweep", "vertical", "other")


def classify_saccades(dx, dy) -> np.ndarray:
    """Saccade type from its horizontal and vertical size in pixels (thresholds for 20-point text, 48 px lines).

    forward: |dy| < 20 and 10 < dx <= 200; regression: |dy| < 20 and -200 <= dx < -10; return sweep: 24 <= dy <= 72 and
    dx < -200; vertical: |dx| < 100 and 24 <= |dy| <= 120; other: the rest.
    """
    dx, dy = np.asarray(dx, float), np.asarray(dy, float)
    return np.select([(np.abs(dy) < 20) & (dx > 10) & (dx <= 200), (np.abs(dy) < 20) & (dx < -10) & (dx >= -200),
                      (dy >= 24) & (dy <= 72) & (dx < -200), (np.abs(dx) < 100) & (np.abs(dy) >= 24) & (np.abs(dy) <= 120)],
                     ["forward", "regression", "return sweep", "vertical"], "other")


def _window_mean(arr, a, z, bin_ms, need):
    i0, i1 = int(math.ceil(a / bin_ms)), int(math.floor(z / bin_ms))
    seg = arr[max(i0, 0):max(i1, 0)]
    ok = np.isfinite(seg)
    return float(seg[ok].mean()) if ok.sum() >= need else np.nan


def saccade_steps(bins: pd.DataFrame, fixations: pd.DataFrame, after: Tuple[float, float] = (20, 120), before: float = 100,
                  late: Tuple[float, float] = (300, 600), max_gap_ms: float = 100, start_after_ms: float = 500,
                  min_fix_ms: float = 80, min_bins: int = 3, min_bins_late: int = 8, means: Optional[pd.Series] = None,
                  classify=classify_saccades) -> pd.DataFrame:
    """Measure the pupil step across every saccade between two retained fixations (stage 3.4).

    Parameters
    ----------
    bins : DataFrame
        Binned trace (:func:`bin`) of the kept trials, before baseline correction.
    fixations : DataFrame
        Fixation table (:func:`read_fixations`). Saccades are the gaps of 0 to ``max_gap_ms`` between consecutive
        retained fixations (at least ``min_fix_ms``, not bordering a blink); saccade size is the difference between the
        two fixation positions.
    after : (start, end)
        Window after landing, in ms, whose mean gives the post-saccade value (paper: 20 to 120 ms).
    before : float
        Length of the window before saccade onset (paper: 100 ms).
    late : (start, end)
        Later window after landing (300 to 600 ms), for the real response that follows the immediate step.
    start_after_ms : float
        Saccades must start at least this long after text onset, and end at least ``late[1]`` before the trial ends.
    min_bins, min_bins_late : int
        Valid bins needed in the before/after windows and in the late window.

    Returns
    -------
    DataFrame
        One row per saccade: reader, item, trial, version, eye, type (see :func:`classify_saccades`), x0, y0, x1, y1,
        dx, dy, gap, start (saccade onset = fixation end), landing (next fixation start), ref (pupil before onset, % of
        reader mean), step (after minus before) and late (late window minus before).
    """
    check_columns(bins, ["reader", "trial", "time", "pupil", "n_valid"], "saccade_steps")
    bin_ms = float((bins.attrs or {}).get("bin_ms", 20))
    rm = means if means is not None else _reader_means(bins)
    ok = ok_mask(bins)
    B = bins.loc[ok, ["reader", "trial", "time", "pupil"]].copy()
    B["v"] = 100 * B["pupil"].to_numpy(float) / B["reader"].map(rm).to_numpy(float)
    if "duration" not in bins.columns:
        raise ValueError("saccade_steps: bins need a 'duration' column (create them with pupilread.bin)")
    info_cols = [c for c in ("reader", "item", "trial", "version", "eye", "duration") if c in bins.columns]
    info = bins.drop_duplicates(["reader", "trial"])[info_cols].rename(columns={"duration": "trial_duration"})
    F = retained_fixations(fixations, min_fix_ms)
    F = F.drop(columns=[c for c in ("item", "version", "eye") if c in F.columns])
    F = F.merge(info, on=["reader", "trial"], how="inner").sort_values(["reader", "trial", "start"], kind="mergesort")
    g = F.groupby(["reader", "trial"], sort=False)
    F = F.assign(ns=g["start"].shift(-1), nx=g["x"].shift(-1), ny=g["y"].shift(-1))
    F["S"] = F["start"] + F["duration"]
    F["L"] = F["ns"]
    F["gap"] = F["L"] - F["S"]
    F["dx"] = F["nx"] - F["x"]
    F["dy"] = F["ny"] - F["y"]
    dur = F["trial_duration"]
    sac = F[(F["gap"] >= 0) & (F["gap"] <= max_gap_ms) & (F["S"] >= start_after_ms) & (F["L"] + late[1] <= dur)].copy()
    sac["type"] = classify(sac["dx"], sac["dy"])
    rows = []
    for (r, tr), s in sac.groupby(["reader", "trial"], sort=False):
        b = B[(B["reader"] == r) & (B["trial"] == tr)]
        if b.empty:
            continue
        idx = (b["time"].to_numpy(float) // bin_ms).astype(int)
        arr = np.full(idx.max() + 60, np.nan)
        arr[idx] = b["v"].to_numpy(float)
        for q in s.itertuples(index=False):
            ref = _window_mean(arr, q.S - before, q.S, bin_ms, min_bins)
            imm = _window_mean(arr, q.L + after[0], q.L + after[1], bin_ms, min_bins)
            lt = _window_mean(arr, q.L + late[0], q.L + late[1], bin_ms, min_bins_late)
            rows.append((r, getattr(q, "item", tr), tr, getattr(q, "version", None), getattr(q, "eye", None), q.type,
                         q.x, q.y, q.nx, q.ny, q.dx, q.dy, q.gap, q.S, q.L, ref, imm - ref, lt - ref))
    cols = ["reader", "item", "trial", "version", "eye", "type", "x0", "y0", "x1", "y1", "dx", "dy", "gap", "start",
            "landing", "ref", "step", "late"]
    out = pd.DataFrame(rows, columns=cols)
    out.attrs = {"after": tuple(after), "before": before, "bin_ms": bin_ms}
    return out


def _ols(X, y):
    c, *_ = np.linalg.lstsq(X, y, rcond=None)
    return c


JOINT_TYPES = ("forward", "regression", "return sweep")
#: Knots (px) of the exploratory horizontal artifact map, for a 1,024-pixel-wide display; the knot at 500 px is the
#: reference (artifact 0).
MAP_KNOTS = tuple(range(0, 1001, 100))


def hat_basis(x, knots) -> np.ndarray:
    """Piecewise-linear (hat) basis of ``x`` at ``knots``: one column per knot, values clamped at the outer knots."""
    x = np.asarray(x, float)
    knots = np.asarray(knots, float)
    eye = np.eye(len(knots))
    return np.column_stack([np.interp(x, knots, eye[j]) for j in range(len(knots))])


def step_slopes(steps: pd.DataFrame, by: Optional[str] = "eye", method: str = "joint", min_saccades: int = 50,
                knots=MAP_KNOTS, reference: float = 500) -> pd.DataFrame:
    """Artifact per pixel of gaze shift, from the saccade steps (stage 3.4).

    Parameters
    ----------
    steps : DataFrame
        Output of :func:`saccade_steps`.
    by : {"eye", "reader", None}
        Estimate slopes per recorded eye (paper), per reader (readers with more than ``min_saccades`` saccades), or
        pooled.
    method : {"joint", "by_type", "map"}
        ``joint``: one regression of the step on horizontal and vertical saccade size over forward saccades,
        regressions and return sweeps (paper). ``by_type`` (exploratory): the horizontal slope from within-line
        saccades only and the vertical slope from vertical saccades only, because return sweeps move gaze left and down
        at once. ``map`` (exploratory): a piecewise-linear map of horizontal position with knots at ``knots`` (the
        knot at ``reference`` fixed at 0) plus a linear vertical slope, fitted to all classified saccades.

    Returns
    -------
    DataFrame
        One row per group: bX and bY (% of the reader mean per pixel), intercept, n_saccades. For ``map``, bX is
        missing and the columns ``x_<knot>`` hold the map (% of the reader mean at each knot).
    """
    q = steps[np.isfinite(steps["step"])]
    groups = [("pooled", q)] if by is None else list(q.groupby(by, sort=True))
    rows = []
    knots = [float(k) for k in knots]
    for gname, d in groups:
        if method == "joint":
            d = d[d["type"].isin(JOINT_TYPES)]
            if by == "reader" and len(d) <= min_saccades:
                continue
            if len(d) < 3:
                continue
            c = _ols(np.column_stack([np.ones(len(d)), d["dx"], d["dy"]]), d["step"].to_numpy(float))
            rows.append({"group": gname, "intercept": c[0], "bX": c[1], "bY": c[2], "n_saccades": len(d)})
        elif method == "by_type":
            wl = d[d["type"].isin(["forward", "regression"])]
            vt = d[d["type"] == "vertical"]
            if len(wl) < 2 or len(vt) < 3:
                continue
            bx = _ols(np.column_stack([np.ones(len(wl)), wl["dx"]]), wl["step"].to_numpy(float))[1]
            by_ = _ols(np.column_stack([np.ones(len(vt)), vt["dx"], vt["dy"]]), vt["step"].to_numpy(float))[2]
            rows.append({"group": gname, "intercept": np.nan, "bX": bx, "bY": by_, "n_saccades": len(wl) + len(vt)})
        elif method == "map":
            d = d[d["type"] != "other"]
            if len(d) < len(knots) + 2:
                continue
            keep = [i for i, k in enumerate(knots) if k != float(reference)]
            H = hat_basis(d["x1"], knots) - hat_basis(d["x0"], knots)
            X = np.column_stack([np.ones(len(d)), H[:, keep], d["dy"].to_numpy(float)])
            c = _ols(X, d["step"].to_numpy(float))
            row = {"group": gname, "intercept": c[0], "bX": np.nan, "bY": c[-1], "n_saccades": len(d)}
            beta = dict(zip([knots[i] for i in keep], c[1:-1]))
            beta[float(reference)] = 0.0
            row.update({f"x_{k:g}": beta[k] for k in knots})
            rows.append(row)
        else:
            raise ValueError("step_slopes: method must be 'joint', 'by_type' or 'map'")
    if not rows:
        raise ValueError(f"step_slopes: too few saccades for method {method!r}"
                         + (" (no vertical saccades)" if method == "by_type" else ""))
    out = pd.DataFrame(rows).set_index("group")
    out.attrs = {"by": by, "method": method, "unit": "% of reader mean per px"}
    if method == "map":
        out.attrs.update(knots=knots, reference=float(reference))
    return out


def regression_slopes(bins: pd.DataFrame, window: Tuple[float, float] = (0, 200), min_baseline_pct: float = 60,
                      time_terms: bool = False, means: Optional[pd.Series] = None) -> pd.Series:
    """Artifact slopes from regressing pupil size on gaze position in the reading data (stage 3.4; Table 2).

    ``time_terms=False``: pooled regression of the baseline-corrected pupil on gaze x and y over all valid bins of the
    analysed trials. ``time_terms=True``: within-trial regression with linear and quadratic time, which absorbs the
    decline of pupil size during reading. Because gaze covaries with progress through the text, these slopes can absorb
    part of a real effect or enlarge it; the saccade steps avoid that (Table 2).

    Returns
    -------
    Series
        bX and bY in pupil units per pixel (the scale of ``bins['pupil']``).
    """
    rm = means if means is not None else _reader_means(bins)
    ok = ok_mask(bins)
    B = bins.loc[ok, ["reader", "trial", "time", "pupil", "gaze_x", "gaze_y"]].copy()
    B["rm"] = B["reader"].map(rm)
    a, b = window
    base = B[(B["time"] < b) & (B["time"] >= a)].groupby(["reader", "trial"])["pupil"].mean().rename("base")
    B = B.join(base, on=["reader", "trial"])
    B = B[100 * B["base"] / B["rm"] >= min_baseline_pct]
    g = B.dropna(subset=["gaze_x", "gaze_y", "base"]).copy()
    if not time_terms:
        y = (g["pupil"] - g["base"]).to_numpy(float)
        c = _ols(np.column_stack([np.ones(len(g)), g["gaze_x"], g["gaze_y"]]), y)
        return pd.Series({"bX": c[1], "bY": c[2]}, name="regression_pooled")
    g["ts"] = g["time"] / 1000.0
    g["t2"] = g["ts"] ** 2
    grp = g.groupby(["reader", "trial"])
    dm = {c: (g[c] - grp[c].transform("mean")).to_numpy(float) for c in ("pupil", "gaze_x", "gaze_y", "ts", "t2")}
    X = np.column_stack([np.ones(len(g)), dm["gaze_x"], dm["gaze_y"], dm["ts"], dm["t2"]])
    c = _ols(X, dm["pupil"])
    return pd.Series({"bX": c[1], "bY": c[2]}, name="regression_within_time")


#: Settings of a measured layout for the geometric model (:func:`read_layout`). Positions are in millimetres, in a frame
#: centred on the eye they were measured from, with x to the right, y up and z towards the screen (Hayes & Petrov, 2016).
LAYOUT_SETTINGS = {
    "image_width": "width of the visible image (mm)",
    "image_height": "height of the visible image (mm)",
    "width_px": "width of the image (pixels)",
    "height_px": "height of the image (pixels)",
    "Sx": "upper-left corner of the image, to the right of the eye (mm; negative to the left)",
    "Sy": "upper-left corner of the image, above the eye (mm)",
    "Sz": "eye to screen (mm)",
    "Cx": "centre of the camera lens, to the right of the eye (mm)",
    "Cy": "centre of the camera lens, above the eye (mm; negative below)",
    "Cz": "centre of the camera lens, in front of the eye (mm)",
    "eye": "point the positions were measured from: 'left' or 'right' eye, or 'midline' between the eyes",
    "eye_separation": "distance between the centres of the two eyes (mm; default 64)",
}
_LAYOUT_NUMBERS = ("image_width", "image_height", "width_px", "height_px", "Sx", "Sy", "Sz", "Cx", "Cy", "Cz")


def read_layout(layout) -> dict:
    """A measured layout of eye, camera and screen for the geometric correction (stage 3.4; Hayes & Petrov, 2016).

    Parameters
    ----------
    layout : str, path or dict
        A CSV file with the columns ``setting`` and ``value``, one row per setting of :data:`LAYOUT_SETTINGS` (other
        columns, such as a unit or a note, are ignored), or a dict with the same keys. ``eye`` (default "left") names
        the point the positions were measured from; the other eye lies ``eye_separation`` mm (default 64) to its side,
        or each eye half of it from the midline.

    Returns
    -------
    dict
        The settings, with numbers as floats.
    """
    if isinstance(layout, dict):
        raw = dict(layout)
    else:
        t = pd.read_csv(layout, dtype=str, skipinitialspace=True)
        t.columns = [str(c).strip().lower() for c in t.columns]
        if not {"setting", "value"} <= set(t.columns):
            raise ValueError(f"read_layout: {layout} needs the columns 'setting' and 'value'")
        raw = {str(k).strip(): str(v).strip() for k, v in zip(t["setting"], t["value"]) if str(k).strip()}
    unknown = sorted(set(raw) - set(LAYOUT_SETTINGS))
    if unknown:
        raise ValueError(f"read_layout: unknown setting(s) {unknown}; expected {list(LAYOUT_SETTINGS)}")
    missing = [k for k in _LAYOUT_NUMBERS if k not in raw]
    if missing:
        raise ValueError(f"read_layout: missing setting(s) {missing}")
    out = {k: float(raw[k]) for k in _LAYOUT_NUMBERS}
    out["eye"] = str(raw.get("eye", "left")).strip().lower()
    out["eye_separation"] = float(raw.get("eye_separation", 64.0))
    if out["eye"] not in ("left", "right", "midline"):
        raise ValueError("read_layout: 'eye' must be 'left', 'right' or 'midline'")
    for k in ("image_width", "image_height", "width_px", "height_px", "Sz", "Cz"):
        if not out[k] > 0:
            raise ValueError(f"read_layout: {k} must be positive")
    return out


def _eye_offset(eye, layout: dict) -> np.ndarray:
    """x position (mm) of each recorded eye relative to the point the layout was measured from."""
    e = pd.Series(np.asarray(eye, dtype=object)).astype(str).str.lower().to_numpy()
    sep = layout["eye_separation"]
    pos = {"left": {"left": 0.0, "right": sep}, "right": {"left": -sep, "right": 0.0},
           "midline": {"left": -sep / 2, "right": sep / 2}}[layout["eye"]]
    bad = sorted(set(e) - set(pos))
    if bad:
        raise ValueError(f"foreshortening: eye must be 'left' or 'right', found {bad}")
    return np.array([pos[v] for v in e], float)


def foreshortening(bins: pd.DataFrame, layout) -> np.ndarray:
    """cos theta for every bin: the factor by which measured pupil area shrinks at the bin's gaze position (stage 3.4).

    theta is the angle between the line from the recorded eye to the camera lens and the line from the eye to the gaze
    position on the screen (Hayes & Petrov, 2016). Gaze pixels are converted to millimetres on the screen with
    the image size of the layout, and each eye's own horizontal position is used (column ``eye``).

    Parameters
    ----------
    bins : DataFrame
        Bins (or samples) with ``gaze_x``, ``gaze_y`` (pixels from the upper-left corner) and ``eye``.
    layout : str, path or dict
        The measured layout (:func:`read_layout`).

    Returns
    -------
    ndarray
        cos theta per row (missing where the gaze position is missing).
    """
    lay = layout if isinstance(layout, dict) and "eye_separation" in layout else read_layout(layout)
    check_columns(bins, ["gaze_x", "gaze_y", "eye"], "foreshortening")
    dx = _eye_offset(bins["eye"], lay)
    tx = lay["Sx"] + bins["gaze_x"].to_numpy(float) * lay["image_width"] / lay["width_px"] - dx
    ty = lay["Sy"] - bins["gaze_y"].to_numpy(float) * lay["image_height"] / lay["height_px"]
    tz = np.full(len(bins), lay["Sz"])
    cx, cy, cz = lay["Cx"] - dx, np.full(len(bins), lay["Cy"]), np.full(len(bins), lay["Cz"])
    num = tx * cx + ty * cy + tz * cz
    return num / (np.sqrt(tx ** 2 + ty ** 2 + tz ** 2) * np.sqrt(cx ** 2 + cy ** 2 + cz ** 2))


def geometric_scale(steps: pd.DataFrame, layout, by: Optional[str] = "eye", pupil_unit: str = "area",
                    min_saccades: int = 50, types=JOINT_TYPES) -> pd.DataFrame:
    """Scale factor of the geometric model, fitted to the saccade steps (stage 3.4; exploratory hybrid correction).

    For every saccade with a measured step, the geometric model predicts the change in measured pupil size between its
    start and landing positions, in % of the reader mean like the step: ref x ((cos theta at landing / cos theta at
    the start) ** p - 1), with p = 1 for pupil area and 0.5 for diameter (:func:`foreshortening`). Regressing the
    measured steps on the predicted ones (with an intercept, over the saccade types of the joint step regression) gives
    the scale factor k per group: k = 1 where the steps follow the model, 0 where they show no foreshortening artifact
    and a negative k where they run against it. ``correct_gaze(method="hybrid")`` divides pupil area by cos theta to
    the power k.

    Parameters
    ----------
    steps : DataFrame
        Output of :func:`saccade_steps` (with the eye of each saccade).
    layout : str, path or dict
        The measured layout (:func:`read_layout`).
    by : {"eye", "reader", None}
        One scale factor per recorded eye, per reader (readers with more than ``min_saccades`` saccades) or pooled.
    pupil_unit : {"area", "diameter"}
        Unit of the pupil trace the steps were measured on.

    Returns
    -------
    DataFrame
        One row per group: k, intercept, r2 (variance of the steps explained by the prediction) and n_saccades.
    """
    lay = layout if isinstance(layout, dict) and "eye_separation" in layout else read_layout(layout)
    check_columns(steps, ["x0", "y0", "x1", "y1", "eye", "ref", "step", "type"], "geometric_scale")
    q = steps[np.isfinite(steps["step"].to_numpy(float)) & steps["type"].isin(types)].copy()
    c0 = foreshortening(q.rename(columns={"x0": "gaze_x", "y0": "gaze_y"}), lay)
    c1 = foreshortening(q.rename(columns={"x1": "gaze_x", "y1": "gaze_y"}), lay)
    p = 0.5 if pupil_unit == "diameter" else 1.0
    q["predicted"] = q["ref"].to_numpy(float) * ((c1 / c0) ** p - 1)
    q = q[np.isfinite(q["predicted"].to_numpy(float))]
    groups = [("pooled", q)] if by is None else list(q.groupby(by, sort=True))
    rows = []
    for gname, d in groups:
        if (by == "reader" and len(d) <= min_saccades) or len(d) < 3:
            continue
        x, y = d["predicted"].to_numpy(float), d["step"].to_numpy(float)
        X = np.column_stack([np.ones(len(d)), x])
        c = _ols(X, y)
        r2 = 1 - float(((y - X @ c) ** 2).sum()) / float(((y - y.mean()) ** 2).sum())
        rows.append({"group": gname, "k": c[1], "intercept": c[0], "r2": r2, "n_saccades": len(d)})
    if not rows:
        raise ValueError("geometric_scale: too few saccades")
    out = pd.DataFrame(rows).set_index("group")
    out.attrs = {"by": by, "method": "hybrid", "pupil_unit": pupil_unit}
    return out


def correct_gaze(bins: pd.DataFrame, slopes=None, method: Optional[str] = None, by: str = "eye",
                 means: Optional[pd.Series] = None, layout=None) -> pd.DataFrame:
    """Remove the gaze-position artifact from every bin, before baseline correction (stage 3.4).

    Parameters
    ----------
    bins : DataFrame
        Binned trace (:func:`bin`). Gaze correction must run before :func:`baseline`, so that the baseline is corrected
        for its own gaze position; a warning is raised if the bins already carry a baseline.
    slopes : DataFrame or Series
        For ``method="steps"``: :func:`step_slopes` output (% of reader mean per pixel, one row per eye or reader, or
        a horizontal map). For ``method="regression"``: :func:`regression_slopes` output (pupil units per pixel). For
        ``method="hybrid"``: :func:`geometric_scale` output (scale factor k per eye or reader).
    method : {None, "steps", "regression", "geometric", "hybrid"}
        None (paper's primary estimate) returns the bins unchanged. "geometric" divides pupil area by cos theta of the
        measured layout (:func:`foreshortening`; Hayes & Petrov, 2016), or pupil diameter by its square root,
        following ``bins.attrs['pupil_unit']``; it needs ``layout`` and no ``slopes``. "hybrid" (exploratory) raises
        cos theta to the power k of :func:`geometric_scale` first; it needs ``layout`` and ``slopes``.
    by : {"eye", "reader", None}
        Which column of the bins selects the row of ``slopes`` (steps and hybrid); None applies one pooled row to all
        bins.
    means : Series, optional
        Reader means for the steps correction (default: :func:`reader_means` of the bins).
    layout : str, path or dict, optional
        The measured layout for ``method="geometric"`` and ``method="hybrid"`` (:func:`read_layout`).

    Returns
    -------
    DataFrame
        The bins with ``pupil_corrected`` (and ``cos_theta`` for the geometric and hybrid corrections); missing gaze
        positions are set to the mean gaze position before the artifact is removed. Bins whose eye or reader has no row
        in ``slopes`` get a missing corrected value.
    """
    if method is None:
        return bins
    if "change" in bins.columns:
        warn_order("correct_gaze(): the bins already have a baseline-corrected 'change'; apply correct_gaze() before "
                   "baseline() and recompute the baseline")
    check_columns(bins, ["gaze_x", "gaze_y", "pupil"], "correct_gaze")
    ok = ok_mask(bins)
    xf = bins["gaze_x"].fillna(bins.loc[ok, "gaze_x"].mean()).to_numpy(float)
    yf = bins["gaze_y"].fillna(bins.loc[ok, "gaze_y"].mean()).to_numpy(float)
    out = bins.copy()

    def group_key(sl):
        sl = sl.copy()
        sl.index = sl.index.astype(str)
        if by is None or (len(sl) == 1 and sl.index[0] == "pooled"):
            return sl, pd.Series(sl.index[0], index=out.index)
        key = out[by].astype(str)
        if by == "eye":
            key = key.str.lower()
            sl.index = sl.index.str.lower()
        return sl, key

    if method == "steps":
        if not isinstance(slopes, pd.DataFrame):
            raise ValueError("correct_gaze(method='steps') needs the DataFrame returned by step_slopes()")
        sl, key = group_key(slopes)
        rm = means if means is not None else _reader_means(bins)
        rmv = out["reader"].map(rm).to_numpy(float)
        byy = key.map(sl["bY"]).to_numpy(float)
        knots = (slopes.attrs or {}).get("knots")
        if (slopes.attrs or {}).get("method") == "map" and knots:
            art = np.full(len(out), np.nan)
            H = hat_basis(xf, knots)
            cols = [f"x_{float(k):g}" for k in knots]
            for g, row in sl.iterrows():
                m = (key == g).to_numpy()
                if m.any():
                    art[m] = H[m] @ row[cols].to_numpy(float) + row["bY"] * yf[m]
        else:
            bx = key.map(sl["bX"]).to_numpy(float)
            art = bx * xf + byy * yf
        out["pupil_corrected"] = out["pupil"].to_numpy(float) - art * rmv / 100.0
    elif method == "regression":
        bx, byy = float(slopes["bX"]), float(slopes["bY"])
        out["pupil_corrected"] = out["pupil"].to_numpy(float) - (bx * xf + byy * yf)
    elif method in ("geometric", "hybrid"):
        if layout is None:
            raise ValueError(f"correct_gaze(method={method!r}) needs layout= (a CSV file or dict; see read_layout)")
        if method == "hybrid" and not (isinstance(slopes, pd.DataFrame) and "k" in slopes.columns):
            raise ValueError("correct_gaze(method='hybrid') needs the DataFrame returned by geometric_scale()")
        check_columns(bins, ["eye"], "correct_gaze")
        c = foreshortening(pd.DataFrame({"gaze_x": xf, "gaze_y": yf, "eye": out["eye"].to_numpy()}), layout)
        if not (c > 0).all():
            warnings.warn("correct_gaze: cos theta is not positive for some bins (check the layout); they are set to "
                          "missing")
            c = np.where(c > 0, c, np.nan)
        power = 0.5 if (bins.attrs or {}).get("pupil_unit", "area") == "diameter" else 1.0
        if method == "hybrid":
            sl, key = group_key(slopes)
            power = power * key.map(sl["k"]).to_numpy(float)
        out["cos_theta"] = c
        out["pupil_corrected"] = out["pupil"].to_numpy(float) / c ** power
    else:
        raise ValueError("correct_gaze: method must be None, 'steps', 'regression', 'geometric' or 'hybrid'")
    return copy_attrs(bins, out, gaze_correction=method)
