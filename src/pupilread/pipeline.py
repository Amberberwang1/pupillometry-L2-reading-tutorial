"""One-call pipeline: settings, per-reader preparation (stages 3.1-3.2), pooled analysis (3.3-3.6) and the R files.

:func:`run_pipeline` runs the stages in the order the paper sets out, gaze correction before baseline correction, with
the settings of a YAML file or dict (:data:`DEFAULTS` are the paper's primary choices). Readers are prepared one at a
time, so that large sample reports never need to be in memory together, and can be cached on disk.
"""
from __future__ import annotations

import copy
import glob
import json
import os
import re
import time
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional

import numpy as np
import pandas as pd

from ._version import __version__
from ._utils import TRIAL_KEY
from .baseline import baseline, low_baselines, reader_means
from .blinks import data_loss, detect_blinks, exclude_trials, interpolate, pad_blinks, summarise
from .gaze import correct_gaze, regression_slopes, saccade_steps, step_slopes
from .io import read_csv, read_eyelink, read_fixations, read_messages
from .levels import bin as bin_samples
from .levels import compare_levels
from .windows import Events, _summarise, event_response, trial_means

#: The paper's primary choices; every setting can be changed in the config (YAML file or dict).
DEFAULTS: Dict = {
    "data": {
        "format": "eyelink",            # "eyelink" (Data Viewer reports) or "csv" (read_csv with "columns")
        "readers": None,                # optional {reader: {"samples": ..., "messages": ..., "fixations": ...}}
        "reader_pattern": None,         # optional regex with one group that extracts the reader ID from a file path
        "design": None,                 # CSV or dict: trial -> item and version (optionally per reader)
        "exclude": None,                # CSV (reader, trial) of trials excluded before analysis, e.g. skimmed texts
        "onset": "DISPLAY_target",      # message at text onset
        "end": "KEYBOARD_endTarget",    # message at the end-of-reading key press
        "eye": "auto",
        "pupil_unit": "area",
        "columns": None,                # read_csv: mapping of our column names to the file's
        "hz": None,
        "missing": 0,
        "sep": ",",
        "drop_duplicates": True,        # drop sample rows that repeat the trial and time stamp of an earlier row
    },
    "display": {"width": 1024, "height": 768, "px_per_degree": None},
    "blinks": {"detect": False, "mad_k": 16, "pad_ms": 100, "pupil_range": [100, 10000]},
    "interpolate": {"max_gap_ms": 1000, "kind": "linear"},
    "trials": {"min_valid": 0.5},
    "bin": {"bin_ms": 20, "min_valid": 0.5},
    "levels": {"min_fix_ms": 80},
    "gaze": {"method": None, "by": "eye", "slopes": "joint", "time_terms": False},
    "baseline": {"window": [0, 200], "method": "subtractive", "scale": "reader_mean"},
    "low_baselines": {"min_pct": 60},
    "trial_means": {"window": [500, 20000], "cut_before_keypress_ms": 0},
    "events": {"blink": {"window": [-200, 2000], "baseline_ms": 100, "kept_only": True, "lag_ms": 1},
               "return_sweep": {"window": [-300, 1000]}},
    "options": "paper",                 # "paper" (Tables 3 and S1), None, or a dict of options (see options_table)
    "export": {"folder": "for_R", "bin_ms": 100, "window": [500, 20000], "reference": None, "scripts": True},
    "plots": True,
}

_FREE = {"data.readers", "data.design", "data.columns", "options", "data.exclude"}


def _deep_update(base: dict, upd: Mapping, path: str = "") -> dict:
    for k, v in upd.items():
        p = path + str(k)
        if k not in base:
            raise ValueError(f"config: unknown setting {p!r}; see pupilread.DEFAULTS")
        if isinstance(base[k], dict) and isinstance(v, Mapping) and p not in _FREE:
            _deep_update(base[k], v, p + ".")
        else:
            base[k] = v
    return base


def load_config(config=None) -> dict:
    """The default settings (:data:`DEFAULTS`) updated with ``config``: a dict, or a path to a YAML or JSON file.

    Unknown settings raise an error, so that a misspelt key cannot silently leave the default in place.
    """
    cfg = copy.deepcopy(DEFAULTS)
    if config is None:
        return cfg
    if isinstance(config, (str, os.PathLike)):
        path = str(config)
        with open(path, encoding="utf-8") as f:
            if path.lower().endswith((".yaml", ".yml")):
                import yaml
                config = yaml.safe_load(f) or {}
            else:
                config = json.load(f)
    if not isinstance(config, Mapping):
        raise ValueError("config must be a dict or a YAML/JSON file")
    if config.get("_resolved"):
        return copy.deepcopy(dict(config))
    out = _deep_update(cfg, config)
    out["_resolved"] = True
    return out


def default_config_yaml() -> str:
    """The default settings as YAML text (``pupilread config`` prints it)."""
    import yaml
    return yaml.safe_dump(DEFAULTS, sort_keys=False, default_flow_style=None)


# ----------------------------------------------------------------------------------------------- prepared data

@dataclass
class PupilData:
    """Prepared data of one or more readers (stages 3.1-3.2).

    Attributes
    ----------
    bins : DataFrame
        20 ms bins of the kept trials (:func:`bin`), with ``pupil`` (blinks removed) and ``pupil_interp``.
    trials : DataFrame
        One row per trial read: data loss, event rates, and ``excluded`` with its ``reason`` (:func:`exclude_trials`).
    fixations : DataFrame or None
        Fixation table of the kept trials (:func:`read_fixations`).
    levels : DataFrame or None
        Per retained fixation, the fixation-report pupil and the mean of the samples inside it (:func:`compare_levels`).
    blink_events : DataFrame or None
        Blink-locked responses per reader, version and lag (``by_reader`` of :func:`event_response`).
    option_bins : dict
        Bins prepared with other sample-level settings, one entry per option that changes them.
    """

    bins: pd.DataFrame
    trials: pd.DataFrame
    fixations: Optional[pd.DataFrame] = None
    levels: Optional[pd.DataFrame] = None
    blink_events: Optional[pd.DataFrame] = None
    option_bins: dict = field(default_factory=dict)

    @property
    def readers(self) -> List[str]:
        return [str(r) for r in pd.unique(self.trials["reader"])]

    @classmethod
    def concat(cls, parts: List["PupilData"]) -> "PupilData":
        """Join the prepared data of several readers."""
        parts = [p for p in parts if p is not None]
        if not parts:
            raise ValueError("PupilData.concat: nothing to join")

        def cat(name):
            xs = [getattr(p, name) for p in parts if getattr(p, name) is not None and len(getattr(p, name))]
            return pd.concat(xs, ignore_index=True) if xs else None

        bins = cat("bins")
        attrs = {k: v for k, v in (parts[0].bins.attrs or {}).items() if k not in ("source",)}
        bins.attrs = attrs
        names = set().union(*[set(p.option_bins) for p in parts])
        ob = {}
        for n in names:
            xs = [p.option_bins[n] for p in parts if n in p.option_bins]
            ob[n] = pd.concat(xs, ignore_index=True)
            ob[n].attrs = {k: v for k, v in (xs[0].attrs or {}).items() if k != "source"}
        return cls(bins, cat("trials"), cat("fixations"), cat("levels"), cat("blink_events"), ob)

    def save(self, folder: str) -> None:
        """Write the tables to ``folder`` (CSV, gzip-compressed) with their settings, for :meth:`load`."""
        os.makedirs(folder, exist_ok=True)
        meta = {"pupilread": __version__, "bins_attrs": _jsonable(self.bins.attrs), "option_bins": {}}
        for name in ("bins", "trials", "fixations", "levels", "blink_events"):
            df = getattr(self, name)
            if df is not None:
                df.to_csv(os.path.join(folder, f"{name}.csv.gz"), index=False)
        for n, df in self.option_bins.items():
            fn = f"option_bins_{re.sub(r'[^A-Za-z0-9_]+', '_', n)}.csv.gz"
            df.to_csv(os.path.join(folder, fn), index=False)
            meta["option_bins"][n] = {"file": fn, "attrs": _jsonable(df.attrs)}
        with open(os.path.join(folder, "pupildata.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=1)

    @classmethod
    def load(cls, folder: str) -> "PupilData":
        """Read tables written by :meth:`save`."""
        with open(os.path.join(folder, "pupildata.json"), encoding="utf-8") as f:
            meta = json.load(f)

        def rd(name):
            p = os.path.join(folder, f"{name}.csv.gz")
            if not os.path.exists(p):
                return None
            return pd.read_csv(p, dtype={"reader": str, "version": str, "eye": str}, low_memory=False)

        bins = rd("bins")
        bins.attrs = meta.get("bins_attrs", {})
        ob = {}
        for n, m in meta.get("option_bins", {}).items():
            d = pd.read_csv(os.path.join(folder, m["file"]), dtype={"reader": str, "version": str, "eye": str})
            d.attrs = m.get("attrs", {})
            ob[n] = d
        return cls(bins, rd("trials"), rd("fixations"), rd("levels"), rd("blink_events"), ob)


def _jsonable(d):
    out = {}
    for k, v in (d or {}).items():
        if isinstance(v, (np.floating, np.integer)):
            v = v.item()
        if isinstance(v, tuple):
            v = list(v)
        try:
            json.dumps(v)
        except TypeError:
            v = str(v)
        out[k] = v
    return out


def _restrict(df: Optional[pd.DataFrame], keys: pd.DataFrame) -> Optional[pd.DataFrame]:
    if df is None:
        return None
    k = pd.MultiIndex.from_frame(keys[TRIAL_KEY].astype(str))
    m = pd.MultiIndex.from_arrays([df["reader"].astype(str), df["trial"].astype(str)]).isin(k)
    return df[m].reset_index(drop=True)


def _clean_and_bin(samples: pd.DataFrame, cfg: dict, exclude=None):
    s = samples
    bl = cfg["blinks"]
    if bl.get("detect"):
        s = detect_blinks(s, mad_k=bl["mad_k"], pupil_range=tuple(bl["pupil_range"]))
    s = pad_blinks(s, pad_ms=bl["pad_ms"], pupil_range=tuple(bl["pupil_range"]))
    ip = cfg.get("interpolate")
    if ip:
        s = interpolate(s, max_gap_ms=ip["max_gap_ms"], kind=ip["kind"])
    loss = data_loss(s, by=None).trials
    excl = exclude if exclude is not None else cfg["data"].get("exclude")
    kept, T = exclude_trials(s, min_valid=cfg["trials"]["min_valid"], exclude=excl, loss=loss)
    if len(kept) == 0:
        raise ValueError("prepare: no trials left after exclusion")
    b = bin_samples(kept, bin_ms=cfg["bin"]["bin_ms"], min_valid=cfg["bin"]["min_valid"])
    return s, kept, T, b


def prepare(samples: pd.DataFrame, fixations: Optional[pd.DataFrame] = None, config=None, exclude=None,
            options: Optional[Mapping] = None) -> PupilData:
    """Stages 3.1-3.2 for the readers in ``samples``: blinks, interpolation, data loss, exclusion, bins and levels.

    Parameters
    ----------
    samples : DataFrame
        Sample table (:func:`read_eyelink` or :func:`read_csv`).
    fixations : DataFrame, optional
        Fixation table (:func:`read_fixations`); needed for :func:`compare_levels`, the saccade steps and the
        fixation-level option.
    config : dict or str, optional
        Settings (see :data:`DEFAULTS`).
    exclude : DataFrame, iterable or CSV path, optional
        Trials to drop before analysis (default: ``config["data"]["exclude"]``).
    options : dict, optional
        Options (see :func:`options_table`); options with ``samples`` settings get their own bins.
    """
    cfg = load_config(config)
    s, kept, T, b = _clean_and_bin(samples, cfg, exclude)
    eb = (cfg.get("events") or {}).get("blink")
    if not (eb and not eb.get("kept_only", True)):
        del s
        s = None
    F = levels = None
    if fixations is not None:
        F = _restrict(fixations, T.loc[~T["excluded"], TRIAL_KEY])
        levels = compare_levels(kept, F, min_fix_ms=cfg["levels"]["min_fix_ms"]).fixations
    ev = None
    if eb:
        src = kept if s is None else s
        ev = event_response(src, "blink", window=tuple(eb["window"]), by="version", baseline_ms=eb["baseline_ms"],
                            means=reader_means(b), lag_ms=eb.get("lag_ms", 1)).by_reader
    del kept, s
    ob = {}
    for name, o in (options or {}).items():
        if isinstance(o, Mapping) and o.get("samples"):
            c2 = _deep_update(copy.deepcopy(cfg), o["samples"])
            ob[name] = _clean_and_bin(samples, c2, exclude)[3]
    return PupilData(b, T, F, levels, ev, ob)


# ----------------------------------------------------------------------------------------------- finding readers

_GENERIC = {"output", "outputs", "data", "reports", "report", "results", "export", "exports", "samples"}
_EXT = (".txt", ".xls", ".tsv", ".csv", ".asc.txt")


def _pick(folder: str, key: str, ref: str, exclude=("sample",)) -> Optional[str]:
    c = [f for f in os.listdir(folder) if not f.startswith(("._", ".")) and key in f.lower()
         and not any(e in f.lower() for e in exclude) and f.lower().endswith(_EXT)]
    if not c:
        return None
    if len(c) == 1:
        return os.path.join(folder, c[0])
    stem = os.path.basename(ref).lower()

    def common(a):
        n = 0
        for x, y in zip(a.lower(), stem):
            if x != y:
                break
            n += 1
        return n
    return os.path.join(folder, sorted(c, key=lambda f: (-common(f), f))[0])


def find_readers(path, config=None) -> List[dict]:
    """The sample report (and the message and fixation reports beside it) of every reader under ``path``.

    Sample reports are files whose names contain "sample"; message and fixation reports are files in the same folder
    whose names contain "mess" and "fix". The reader ID is taken from ``config["data"]["reader_pattern"]`` (a regular
    expression with one group, applied to the path) if given, else from the name of the folder holding the report
    (folder names such as "Output" are skipped), else from the file name.

    Returns
    -------
    list of dict
        One dict per reader with keys reader, samples, messages and fixations (paths or None).
    """
    cfg = load_config(config)
    rd = cfg["data"].get("readers")
    if rd:
        return [{"reader": str(r), "samples": v["samples"], "messages": v.get("messages"),
                 "fixations": v.get("fixations")} for r, v in rd.items()]
    path = str(path)
    if os.path.isfile(path):
        files = [os.path.abspath(path)]
    else:
        files = sorted(os.path.abspath(f) for f in glob.glob(os.path.join(path, "**", "*"), recursive=True)
                       if os.path.isfile(f) and "sample" in os.path.basename(f).lower()
                       and not os.path.basename(f).startswith(("._", ".")) and f.lower().endswith(_EXT))
    if not files:
        raise ValueError(f"find_readers: no sample report (a file whose name contains 'sample') under {path}")
    pat = cfg["data"].get("reader_pattern")
    folders = [os.path.dirname(os.path.abspath(f)) for f in files]
    own_folder = len(set(folders)) == len(folders)
    out = []
    for f, d in zip(files, folders):
        if pat:
            m = re.search(pat, f.replace("\\", "/"))
            if not m:
                raise ValueError(f"find_readers: reader_pattern {pat!r} does not match {f}")
            reader = m.group(1)
        elif own_folder and len(files) > 1:
            parts = [p for p in d.replace("\\", "/").split("/") if p]
            name = next((p for p in reversed(parts) if p.lower() not in _GENERIC), parts[-1])
            reader = name
        else:
            stem = os.path.splitext(os.path.basename(f))[0]
            reader = re.sub(r"[ _-]*(sample|samples)[ _-]*(report)?[ _-]*", "", stem, flags=re.I)
            if not reader:                     # a generic name such as "sample_report.txt": use the folder name
                parts = [p for p in d.replace("\\", "/").split("/") if p]
                reader = next((p for p in reversed(parts) if p.lower() not in _GENERIC), stem)
        out.append({"reader": reader, "samples": f, "messages": _pick(d, "mess", f), "fixations": _pick(d, "fix", f)})
    ids = [o["reader"] for o in out]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise ValueError(f"find_readers: reader IDs {dup} occur more than once; set data.reader_pattern")
    return out


def read_reader(job: Mapping, config=None):
    """Read one reader's samples and fixations as :func:`find_readers` lists them."""
    cfg = load_config(config)
    dc = cfg["data"]
    if dc["format"] == "csv":
        if not dc.get("columns"):
            raise ValueError("data.format 'csv' needs data.columns (see read_csv)")
        s = read_csv(job["samples"], dc["columns"], hz=dc.get("hz"), missing=dc.get("missing", 0), sep=dc.get("sep", ","),
                     reader=job["reader"], design=dc.get("design"), pupil_unit=dc.get("pupil_unit", "diameter"))
        return s, None
    msg = read_messages(job["messages"]) if job.get("messages") else None
    s = read_eyelink(job["samples"], messages=msg, onset=dc["onset"], end=dc["end"], eye=dc["eye"], reader=job["reader"],
                     design=dc.get("design"), pupil_unit=dc["pupil_unit"], drop_duplicates=dc.get("drop_duplicates", True))
    f = None
    if job.get("fixations"):
        f = read_fixations(job["fixations"], messages=msg, onset=dc["onset"], end=dc["end"], reader=job["reader"],
                           design=dc.get("design"))
        f["eye"] = s["eye"].iat[0] if len(s) else None
    return s, f


def prepare_readers(path, config=None, cache: Optional[str] = None, verbose: bool = True) -> PupilData:
    """Read and prepare every reader under ``path`` one at a time (see :func:`find_readers` and :func:`prepare`).

    With ``cache``, each reader's prepared data are written to ``cache/<reader>`` and read back on later runs, so an
    interrupted run resumes and the pooled stages can run on another machine without the raw reports.
    """
    cfg = load_config(config)
    opts = _resolve_options(cfg)
    parts = []
    jobs = find_readers(path, cfg) if path is not None else []
    if path is None and cache:
        jobs = [{"reader": r} for r in sorted(os.listdir(cache)) if os.path.exists(os.path.join(cache, r, "pupildata.json"))]
    for job in jobs:
        t0 = time.time()
        folder = os.path.join(cache, str(job["reader"])) if cache else None
        if folder and os.path.exists(os.path.join(folder, "pupildata.json")):
            parts.append(PupilData.load(folder))
            if verbose:
                print(f"reader {job['reader']}: read from cache")
            continue
        if "samples" not in job:
            continue
        s, f = read_reader(job, cfg)
        p = prepare(s, f, cfg, options=opts)
        if folder:
            p.save(folder)
        parts.append(p)
        if verbose:
            n_ex = int(p.trials["excluded"].sum())
            print(f"reader {job['reader']}: {len(p.trials)} trials, {n_ex} excluded, {len(s):,} samples, "
                  f"{time.time() - t0:.0f} s", flush=True)
        del s, f
    if not parts:
        raise ValueError("prepare_readers: no readers found")
    return PupilData.concat(parts)


def _resolve_options(cfg):
    o = cfg.get("options")
    if o is None or o is False:
        return {}
    if isinstance(o, str):
        if o != "paper":
            raise ValueError("config: options must be 'paper', None or a dict")
        from .options import PAPER_OPTIONS
        return dict(PAPER_OPTIONS)
    return dict(o)


# ----------------------------------------------------------------------------------------------- pooled stages

@dataclass
class Result:
    """Everything :func:`run_pipeline` computed; ``files`` lists what it wrote."""

    data: PupilData
    bins: pd.DataFrame
    trials: pd.DataFrame
    low_baselines: pd.DataFrame
    loss: pd.DataFrame
    levels: dict
    steps: Optional[pd.DataFrame]
    slopes: Optional[pd.DataFrame]
    options: Optional[pd.DataFrame]
    events: dict
    config: dict
    files: dict = field(default_factory=dict)


def levels_summary(levels: Optional[pd.DataFrame], trials: Optional[pd.DataFrame] = None) -> dict:
    """Agreement of fixation-report and sample pupil values over fixations, and the share of reading time covered."""
    if levels is None or not len(levels):
        return {}
    ok = np.isfinite(levels["pupil"]) & np.isfinite(levels["pupil_samples"]) & (levels["n_valid"] > 0)
    out = {"r": float(np.corrcoef(levels.loc[ok, "pupil"], levels.loc[ok, "pupil_samples"])[0, 1]) if ok.sum() > 2 else np.nan,
           "mean_abs_diff": float((levels.loc[ok, "pupil"] - levels.loc[ok, "pupil_samples"]).abs().mean()),
           "n_fixations": int(ok.sum())}
    if trials is not None and "duration_s" in trials.columns:
        cov = levels.groupby(TRIAL_KEY)["duration"].sum().reset_index()
        for c in TRIAL_KEY:
            cov[c] = cov[c].astype(str)
        t = trials[TRIAL_KEY + ["duration_s"]].copy()
        for c in TRIAL_KEY:
            t[c] = t[c].astype(str)
        cov = cov.merge(t, on=TRIAL_KEY)
        share = cov["duration"] / (cov["duration_s"] * 1000)
        out.update(coverage_mean=float(share.mean()), coverage_sd=float(share.std()))
    return out


def summarise_events(by_reader: Optional[pd.DataFrame], by: str = "version") -> Optional[Events]:
    """Pool event-locked responses prepared per reader (``PupilData.blink_events``) into the summary table."""
    if by_reader is None or not len(by_reader):
        return None
    lv = by if by in by_reader.columns else "level"
    return Events(_summarise(by_reader, lv), by_reader)


def analyse(data: PupilData, config=None) -> Result:
    """Stages 3.3-3.6 on prepared data: gaze correction, baseline, low baselines, trial means, events and options."""
    cfg = load_config(config)
    bins = data.bins
    rm = reader_means(bins)
    steps = slopes = None
    if data.fixations is not None and len(data.fixations):
        steps = saccade_steps(bins, data.fixations, means=rm)
    g = cfg["gaze"]
    if g.get("method") == "steps":
        if steps is None:
            raise ValueError("gaze.method 'steps' needs fixation reports")
        slopes = step_slopes(steps, by=g.get("by", "eye"), method=g.get("slopes", "joint"))
        bins = correct_gaze(bins, slopes, method="steps", by=g.get("by", "eye"), means=rm)
    elif g.get("method") == "regression":
        slopes = regression_slopes(bins, window=tuple(cfg["baseline"]["window"]), min_baseline_pct=cfg["low_baselines"]["min_pct"] or 0,
                                   time_terms=g.get("time_terms", False), means=rm).to_frame().T
        bins = correct_gaze(bins, slopes.iloc[0], method="regression")
    elif g.get("method") is not None:
        raise ValueError("gaze.method must be null, 'steps' or 'regression'")
    elif steps is not None:
        try:
            slopes = step_slopes(steps, by=g.get("by", "eye"), method=g.get("slopes", "joint"))
        except ValueError as e:
            warnings.warn(f"analyse: no step slopes ({e})")
    bc = cfg["baseline"]
    b = baseline(bins, window=tuple(bc["window"]), method=bc["method"], scale=bc["scale"], means=rm)
    lowb = low_baselines(b, min_pct=cfg["low_baselines"]["min_pct"])
    tm = cfg["trial_means"]
    trials = trial_means(b, window=tuple(tm["window"]) if tm["window"][1] is not None else (tm["window"][0], None),
                         cut_before_keypress_ms=tm["cut_before_keypress_ms"])
    info = [c for c in ("pct_valid", "duration_s", "blink_rate", "saccade_rate") if c in data.trials.columns]
    L = data.trials[TRIAL_KEY + info].copy()
    trials = trials.assign(_r=trials["reader"].astype(str), _t=trials["trial"].astype(str)).merge(
        L.assign(_r=L["reader"].astype(str), _t=L["trial"].astype(str)).drop(columns=TRIAL_KEY), on=["_r", "_t"],
        how="left").drop(columns=["_r", "_t"])
    kept = data.trials[~data.trials["excluded"]]
    loss = summarise(kept, by="version") if "version" in kept.columns and kept["version"].nunique() > 1 else pd.DataFrame()
    events = {}
    be = summarise_events(data.blink_events, "version")
    if be is not None:
        events["blink"] = be
    er = (cfg.get("events") or {}).get("return_sweep")
    if er and steps is not None and len(steps):
        events["return_sweep"] = event_response(data.bins, "return_sweep", window=tuple(er["window"]), saccades=steps,
                                                by="eye", means=rm)
    opts = _resolve_options(cfg)
    table = None
    if opts:
        from .options import options_table
        table = options_table(data, opts, config=cfg, steps=steps)
    return Result(data, b, trials, lowb, loss, levels_summary(data.levels, data.trials), steps, slopes, table, events, cfg)


def run_pipeline(path, config=None, out: Optional[str] = None, cache: Optional[str] = None,
                 verbose: bool = True) -> Result:
    """Run the whole pipeline from the reports under ``path`` and write the files for R (the paper's quick start).

    Parameters
    ----------
    path : str
        A sample report, or a folder searched for the reports of every reader (see :func:`find_readers`). None reads
        prepared readers from ``cache`` only.
    config : dict or str, optional
        Settings, as a dict or a YAML/JSON file; :data:`DEFAULTS` are the paper's primary choices.
    out : str, optional
        Output folder (default: ``pupilread_output`` next to ``path``). The R files go to ``out/<export.folder>``,
        tables to ``out/tables`` and check plots to ``out/figures``.
    cache : str, optional
        Folder for per-reader prepared data (see :func:`prepare_readers`).

    Returns
    -------
    Result
        The tables of every stage and the list of files written.
    """
    from .export import export_for_r

    cfg = load_config(config)
    t0 = time.time()
    data = prepare_readers(path, cfg, cache=cache, verbose=verbose)
    res = analyse(data, cfg)
    if out is None:
        base = path if (path is not None and os.path.isdir(str(path))) else os.path.dirname(os.path.abspath(str(path or cache)))
        out = os.path.join(str(base), "pupilread_output")
    os.makedirs(out, exist_ok=True)
    ex = cfg["export"]
    w = ex.get("window") or cfg["trial_means"]["window"]
    trial_table = res.options if res.options is not None else res.trials
    res.files.update(export_for_r(trial_table, res.bins, os.path.join(out, ex["folder"]), bin_ms=ex["bin_ms"],
                                  window=tuple(w), reference=ex.get("reference"), scripts=ex.get("scripts", True),
                                  config=cfg))
    res.files.update(_write_tables(res, os.path.join(out, "tables")))
    if cfg.get("plots"):
        res.files.update(_write_plots(res, os.path.join(out, "figures")))
    summ = _summary(res)
    sp = os.path.join(out, "summary.json")
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(summ, f, indent=1, default=str)
    res.files["summary"] = sp
    if verbose:
        print(f"pupilread {__version__}: {summ['readers']} readers, {summ['trials_kept']} kept and "
              f"{summ['trials_analysed']} analysed trials; files in {out} ({time.time() - t0:.0f} s)")
    return res


def _write_tables(res: Result, folder: str) -> dict:
    os.makedirs(folder, exist_ok=True)
    files = {}

    def w(name, df, **kw):
        if df is None or (hasattr(df, "__len__") and not len(df)):
            return
        p = os.path.join(folder, name)
        df.to_csv(p, **kw)
        files[name] = p
    w("trials_data_loss.csv", res.data.trials, index=False)
    w("data_loss_by_version.csv", res.loss, index=False)
    w("low_baselines.csv", res.low_baselines, index=False)
    w("trial_means.csv", res.trials, index=False)
    w("saccade_steps.csv.gz", res.steps, index=False)
    w("step_slopes.csv", res.slopes, index=True)
    if res.data.levels is not None:
        w("levels_fixations.csv.gz", res.data.levels, index=False)
    for k, e in res.events.items():
        w(f"events_{k}.csv", e.summary, index=False)
        w(f"events_{k}_by_reader.csv.gz", e.by_reader, index=False)
    return files


def _write_plots(res: Result, folder: str) -> dict:
    from .plots import plot_baselines, plot_gaze, plot_grand_mean, plot_quality, plot_trials

    os.makedirs(folder, exist_ok=True)
    files = {}

    def save(fig, name):
        p = os.path.join(folder, name)
        fig.savefig(p, dpi=200, bbox_inches="tight", facecolor="white")
        files[name] = p
        import matplotlib.pyplot as plt
        plt.close(fig)
    try:
        save(plot_trials(res.bins), "check_trials.png")
        save(plot_baselines(res.low_baselines, min_pct=res.config["low_baselines"]["min_pct"] or 0), "check_baselines.png")
        save(plot_grand_mean(res.bins, min_readers=min(20, max(1, len(res.data.readers) // 2))), "grand_mean.png")
        kept = res.data.trials[~res.data.trials["excluded"]]
        if "version" in kept.columns and kept["version"].notna().any():
            save(plot_quality(kept), "check_quality.png")
            save(plot_gaze(res.bins), "check_gaze.png")
    except Exception as e:  # plots are checks; a failure must not lose the R files
        warnings.warn(f"run_pipeline: a check plot failed: {e}")
    return files


def _summary(res: Result) -> dict:
    T = res.data.trials
    lb = res.low_baselines
    mp = res.config["low_baselines"]["min_pct"]
    analysed = int((lb["baseline_pct"] >= (mp if mp is not None else -np.inf)).sum())
    out = {"pupilread": __version__, "readers": len(res.data.readers), "trials_read": int(len(T)),
           "trials_excluded": int(T["excluded"].sum()), "trials_kept": int((~T["excluded"]).sum()),
           "trials_with_baseline": int(np.isfinite(lb["baseline_pct"]).sum()), "trials_analysed": analysed,
           "exclusion_reasons": T.loc[T["excluded"], "reason"].value_counts().to_dict(),
           "levels": res.levels}
    kept = T[~T["excluded"]]
    for c in ("pct_invalid", "pct_blink_pad", "pct_valid", "blink_rate", "saccade_rate"):
        if c in kept.columns:
            out[f"mean_{c}"] = float(kept.groupby("reader")[c].mean().mean())
    if res.slopes is not None:
        out["step_slopes"] = res.slopes.reset_index().to_dict("records")
    out["config"] = {k: v for k, v in res.config.items() if k != "_resolved"}
    return out
