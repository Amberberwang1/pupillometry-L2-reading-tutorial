"""Stage 3.1, reading data: EyeLink Data Viewer reports and generic sample files into the sample table.

Every reader returns the same columns (``pupilread.SAMPLE_COLUMNS``): reader, item, trial, version, eye, time (ms from
text onset), pupil (as recorded), gaze_x, gaze_y (screen pixels), in_blink, in_saccade (tracker event flags) and
trial_end (ms from text onset to the end-of-reading key press). All later functions use only these columns, so they do
not depend on the eye tracker.
"""
from __future__ import annotations

import os
import re
import warnings
from typing import Callable, Mapping, Optional, Union

import numpy as np
import pandas as pd

from ._utils import SAMPLE_COLUMNS, copy_attrs, sampling_rate, sort_trials

PathLike = Union[str, "os.PathLike[str]"]
EYE_FIELDS = ["PUPIL_SIZE", "GAZE_X", "GAZE_Y", "IN_BLINK", "IN_SACCADE"]


def _clean(name: str) -> str:
    return str(name).replace("﻿", "").strip()


def _header(path: PathLike, sep: str, encoding: str):
    with open(path, encoding=encoding, errors="replace") as f:
        return [_clean(c) for c in f.readline().rstrip("\r\n").split(sep)]


def _read_columns(path, wanted, sep="\t", encoding="utf-8-sig", text=(), chunksize=None, keep=None):
    """Read only the ``wanted`` columns of a Data Viewer report ('.' = missing).

    With ``chunksize``, the file is read in chunks of that many rows and ``keep(chunk)`` may drop rows (or columns)
    from each chunk, so that sample reports of several gigabytes can be read with little memory.
    """
    wanted = set(wanted)
    with open(path, encoding=encoding, errors="replace") as f:
        raw = f.readline().rstrip("\r\n").split(sep)
    names = {_clean(c): c for c in raw}
    dtype = {names[c]: str for c in text if c in names}
    rd = pd.read_csv(path, sep=sep, usecols=lambda c: _clean(c) in wanted, na_values=["."], keep_default_na=True,
                     encoding=encoding, dtype=dtype, chunksize=chunksize)
    parts = []
    for df in (rd if chunksize else [rd]):
        df.columns = [_clean(c) for c in df.columns]
        for c in df.columns:
            if c not in text:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        if keep is not None:
            df = keep(df)
        parts.append(df)
    if chunksize:
        rd.close()
    return pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0]


def _reader_id(reader, labels, path) -> str:
    """The reader ID: as given, else the recording session label of the report, else the file name."""
    if reader is not None:
        return str(reader)
    if labels:
        return max(labels, key=labels.get)
    stem = os.path.splitext(os.path.basename(str(path)))[0]
    return re.sub(r"[ _-]*(sample|samples|fixation|fixations|message|messages)[ _-]*(report)?[ _-]*", "", stem,
                  flags=re.I) or stem


def read_design(design) -> Optional[pd.DataFrame]:
    """Return a design table (columns reader?, trial and/or item, version) from a DataFrame, dict or CSV path.

    A dict maps trial (or item) numbers to version labels and applies to every reader.
    """
    if design is None:
        return None
    if isinstance(design, Mapping):
        return pd.DataFrame({"trial": list(design.keys()), "version": [str(v) for v in design.values()]})
    if isinstance(design, (str, os.PathLike)):
        design = pd.read_csv(design, dtype={"reader": str, "version": str})
    d = design.copy()
    if "reader" in d.columns:
        d["reader"] = d["reader"].astype(str)
    if "trial" not in d.columns and "item" in d.columns:
        d["trial"] = d["item"]
    if "item" not in d.columns:
        d["item"] = d["trial"]
    if "version" not in d.columns:
        raise ValueError("design: a 'version' column is required")
    d["version"] = d["version"].astype(str)
    return d


def _design_for(design: Optional[pd.DataFrame], reader: str) -> Optional[pd.DataFrame]:
    if design is None:
        return None
    if "reader" in design.columns:
        d = design[design["reader"] == str(reader)]
        if d.empty:
            raise ValueError(f"design has no rows for reader {reader!r}")
        return d
    return design


def _apply_design(df: pd.DataFrame, design: Optional[pd.DataFrame], reader: str) -> pd.DataFrame:
    d = _design_for(design, reader)
    if d is None:
        df["item"] = df["trial"]
        df["version"] = np.nan
        return df
    d = d[["trial", "item", "version"]].drop_duplicates("trial").copy()
    d["trial"] = _as_int_if_numeric(d["trial"])
    d["item"] = _as_int_if_numeric(d["item"])
    df = df.copy()
    df["trial"] = _as_int_if_numeric(df["trial"])
    return df.merge(d, on="trial", how="inner")


def _as_int_if_numeric(s: pd.Series) -> pd.Series:
    """Convert a column to int when every value is a whole number, else leave it as text."""
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().all() and np.all(np.mod(num.to_numpy(float), 1) == 0):
        return num.astype(int)
    return s.astype(str)


def read_messages(path: PathLike, encoding: str = "utf-8-sig") -> pd.DataFrame:
    """Read a Data Viewer message report into columns trial, text and time (ms from trial start)."""
    m = _read_columns(path, ["TRIAL_INDEX", "CURRENT_MSG_TEXT", "CURRENT_MSG_TIME"], encoding=encoding,
                      text=("CURRENT_MSG_TEXT",))
    return pd.DataFrame({"trial": m["TRIAL_INDEX"].astype("Int64"), "text": m["CURRENT_MSG_TEXT"].astype(str).str.strip(),
                         "time": m["CURRENT_MSG_TIME"].astype(float)})


def trial_windows(messages: pd.DataFrame, onset: str = "DISPLAY_target", end: str = "KEYBOARD_endTarget") -> pd.DataFrame:
    """Text onset and end-of-reading times per trial (ms from trial start), from a message table.

    The first occurrence of each message in a trial is used. Trials without both messages are left out.
    """
    on = messages[messages["text"] == onset].groupby("trial")["time"].min().rename("onset")
    off = messages[messages["text"] == end].groupby("trial")["time"].min().rename("end")
    w = pd.concat([on, off], axis=1, join="inner").reset_index()
    w["trial"] = w["trial"].astype(int)
    return w


def read_eyelink(path: PathLike, messages: Optional[Union[PathLike, pd.DataFrame]] = None, onset: str = "DISPLAY_target",
                 end: str = "KEYBOARD_endTarget", eye: str = "auto", reader: Optional[str] = None, design=None,
                 pupil_unit: str = "area", encoding: str = "utf-8-sig", chunksize: Optional[int] = 500_000,
                 drop_duplicates: bool = True) -> pd.DataFrame:
    """Read an EyeLink Data Viewer sample report into the sample table (stage 3.1).

    Parameters
    ----------
    path : str or path
        Sample report exported from Data Viewer (tab-separated, '.' for missing values). Only the columns needed are
        read: TRIAL_INDEX, TIMESTAMP, TRIAL_START_TIME, EYE_TRACKED and, for each eye, PUPIL_SIZE, GAZE_X, GAZE_Y,
        IN_BLINK and IN_SACCADE (for example ``RIGHT_PUPIL_SIZE``).
    messages : str, path or DataFrame, optional
        Message report (or the table from :func:`read_messages`) giving the text onset and the end-of-reading key press
        of each trial. Without it, a ``SAMPLE_MESSAGE`` column is used if the report has one, otherwise the whole trial.
    onset, end : str
        Message texts that mark text onset and the end-of-reading key press (our study: ``DISPLAY_target`` and
        ``KEYBOARD_endTarget``).
    eye : {"auto", "left", "right"}
        Eye to read. ``"auto"`` takes the eye named in EYE_TRACKED in most samples, or else the eye with more pupil data.
    reader : str, optional
        Reader identifier; defaults to the report's RECORDING_SESSION_LABEL (the EDF session name), else the file name.
    design : DataFrame, dict or CSV path, optional
        Table with columns trial (TRIAL_INDEX) and/or item, version and optionally reader; trials missing from it (such as
        practice texts) are dropped. Without a design, item = trial and version is missing.
    pupil_unit : {"area", "diameter"}
        Unit set in the EyeLink recording; stored in ``attrs['pupil_unit']`` (see :func:`to_diameter`).
    chunksize : int or None
        Rows read at a time; samples outside the text-onset-to-key-press window are dropped chunk by chunk, so that
        reports of several gigabytes fit in memory. None reads the file at once.
    drop_duplicates : bool
        Drop rows that repeat the trial and time stamp of an earlier row (some exports contain every sample twice),
        with a warning. Duplicated rows would otherwise shorten blink padding and other durations counted in samples.

    Returns
    -------
    DataFrame
        The sample table: one row per sample from text onset to the key press, ``time`` in ms from text onset.
    """
    head = _header(path, "\t", encoding)
    eyes = ["RIGHT", "LEFT"]
    label_col = "RECORDING_SESSION_LABEL" if (reader is None and "RECORDING_SESSION_LABEL" in head) else None
    missing = [c for c in ("TRIAL_INDEX", "TIMESTAMP") if c not in head]
    if missing:
        raise ValueError(f"read_eyelink: {path} lacks {missing}; export a Data Viewer sample report")
    if eye != "auto" and eye.upper() not in eyes:
        raise ValueError("eye must be 'auto', 'left' or 'right'")
    has_start = "TRIAL_START_TIME" in head
    # text onset and key press of every trial (ms from trial start)
    win = None
    if messages is not None:
        msg = messages if isinstance(messages, pd.DataFrame) else read_messages(messages, encoding=encoding)
        win = trial_windows(msg, onset, end)
    elif "SAMPLE_MESSAGE" in head and has_start:
        def only_msgs(df):
            df = df[df["SAMPLE_MESSAGE"].notna()]
            return pd.DataFrame({"trial": df["TRIAL_INDEX"].astype(int), "text": df["SAMPLE_MESSAGE"].astype(str).str.strip(),
                                 "time": (df["TIMESTAMP"] - df["TRIAL_START_TIME"]).to_numpy(float)})
        msg = _read_columns(path, ["TRIAL_INDEX", "TIMESTAMP", "TRIAL_START_TIME", "SAMPLE_MESSAGE"], encoding=encoding,
                            text=("SAMPLE_MESSAGE",), chunksize=chunksize, keep=only_msgs)
        win = trial_windows(msg, onset, end)
    wanted = ["TRIAL_INDEX", "TIMESTAMP", "TRIAL_START_TIME", "EYE_TRACKED"] + ([label_col] if label_col else [])
    use_eyes = eyes if eye == "auto" else [eye.upper()]
    wanted += [f"{e}_{f}" for e in use_eyes for f in EYE_FIELDS]
    counts = {}
    labels = {}

    def keep(df):
        if label_col and label_col in df.columns:
            for k, v in df[label_col].astype(str).str.strip().value_counts().items():
                labels[k] = labels.get(k, 0) + int(v)
            df = df.drop(columns=label_col)
        if "EYE_TRACKED" in df.columns:
            for k, v in df["EYE_TRACKED"].astype(str).str.upper().value_counts().items():
                counts[k] = counts.get(k, 0) + int(v)
            df = df.drop(columns="EYE_TRACKED")
        if win is not None and has_start:
            trel = (df["TIMESTAMP"] - df["TRIAL_START_TIME"]).to_numpy(float)
            on = df["TRIAL_INDEX"].map(win.set_index("trial")["onset"]).to_numpy(float)
            off = df["TRIAL_INDEX"].map(win.set_index("trial")["end"]).to_numpy(float)
            df = df[(trel >= on) & (trel <= off)]
        return df
    S = _read_columns(path, wanted, encoding=encoding, text=("EYE_TRACKED", "RECORDING_SESSION_LABEL"),
                      chunksize=chunksize, keep=keep)
    reader = _reader_id(reader, labels, path)
    # eye
    if eye == "auto":
        if counts:
            share_left = sum(v for k, v in counts.items() if "LEFT" in k) / max(sum(counts.values()), 1)
            e = "LEFT" if share_left > 0.5 else "RIGHT"
        else:
            n = {x: S[f"{x}_PUPIL_SIZE"].notna().sum() if f"{x}_PUPIL_SIZE" in S.columns else -1 for x in eyes}
            e = max(n, key=n.get)
    else:
        e = eye.upper()
    if f"{e}_PUPIL_SIZE" not in S.columns:
        raise ValueError(f"read_eyelink: no {e}_PUPIL_SIZE column in {path}")
    # trial-relative time
    if has_start:
        trel = S["TIMESTAMP"] - S["TRIAL_START_TIME"]
    else:
        trel = S["TIMESTAMP"] - S.groupby("TRIAL_INDEX")["TIMESTAMP"].transform("min")
    S = S.assign(trel=trel.to_numpy(float), TRIAL_INDEX=S["TRIAL_INDEX"].astype(int))
    if win is None:
        g = S.groupby("TRIAL_INDEX")["trel"]
        win = pd.DataFrame({"trial": g.min().index.astype(int), "onset": g.min().to_numpy(), "end": g.max().to_numpy()})
    S = S.merge(win, left_on="TRIAL_INDEX", right_on="trial", how="inner")
    S = S[(S["trel"] >= S["onset"]) & (S["trel"] <= S["end"])]
    S = S.sort_values(["TRIAL_INDEX", "TIMESTAMP"], kind="mergesort")
    if drop_duplicates:
        dup = S.duplicated(["TRIAL_INDEX", "TIMESTAMP"])
        if dup.any():
            warnings.warn(f"read_eyelink: {path}: dropped {int(dup.sum()):,} samples whose trial and time stamp repeat an "
                          "earlier sample (duplicated rows in the report)")
            S = S[~dup.to_numpy()]
    out = pd.DataFrame({
        "reader": reader,
        "trial": S["TRIAL_INDEX"].to_numpy(int),
        "eye": e.lower(),
        "time": (S["trel"] - S["onset"]).to_numpy(float),
        "pupil": S[f"{e}_PUPIL_SIZE"].to_numpy(float),
        "gaze_x": S[f"{e}_GAZE_X"].to_numpy(float) if f"{e}_GAZE_X" in S.columns else np.nan,
        "gaze_y": S[f"{e}_GAZE_Y"].to_numpy(float) if f"{e}_GAZE_Y" in S.columns else np.nan,
        "in_blink": (np.nan_to_num(S[f"{e}_IN_BLINK"].to_numpy(float)) >= 1) if f"{e}_IN_BLINK" in S.columns else False,
        "in_saccade": (np.nan_to_num(S[f"{e}_IN_SACCADE"].to_numpy(float)) >= 1) if f"{e}_IN_SACCADE" in S.columns else False,
        "trial_end": (S["end"] - S["onset"]).to_numpy(float),
    })
    out = _apply_design(out, read_design(design), reader)
    out = out[SAMPLE_COLUMNS]
    dt = np.diff(out["time"].to_numpy(float))
    dt = dt[dt > 0]
    hz = float(round(1000.0 / np.median(dt), 3)) if dt.size else np.nan
    out.attrs = {"pupil_unit": pupil_unit, "hz": hz, "source": str(path), "tracker": "EyeLink"}
    return sort_trials(out)


def read_fixations(path: PathLike, messages: Optional[Union[PathLike, pd.DataFrame]] = None,
                   onset: str = "DISPLAY_target", end: str = "KEYBOARD_endTarget", reader: Optional[str] = None,
                   design=None, encoding: str = "utf-8-sig") -> pd.DataFrame:
    """Read an EyeLink Data Viewer fixation report into a fixation table, times in ms from text onset.

    Columns: reader, item, trial, version, start, end, duration, x, y, pupil, blink_around (NONE, BEFORE, AFTER or
    BOTH) and ia (interest area, if exported). Duplicate rows are dropped. Use the same ``messages`` and ``design`` as
    for :func:`read_eyelink` so that fixations and samples share the time origin.
    """
    wanted = ["TRIAL_INDEX", "CURRENT_FIX_START", "CURRENT_FIX_END", "CURRENT_FIX_DURATION", "CURRENT_FIX_PUPIL",
              "CURRENT_FIX_X", "CURRENT_FIX_Y", "CURRENT_FIX_BLINK_AROUND", "CURRENT_FIX_INTEREST_AREA_ID"]
    if reader is None:
        wanted.append("RECORDING_SESSION_LABEL")
    F = _read_columns(path, wanted, encoding=encoding, text=("CURRENT_FIX_BLINK_AROUND", "RECORDING_SESSION_LABEL"))
    labels = {}
    if "RECORDING_SESSION_LABEL" in F.columns:
        labels = F["RECORDING_SESSION_LABEL"].astype(str).str.strip().value_counts().to_dict()
        F = F.drop(columns="RECORDING_SESSION_LABEL")
    F = F.drop_duplicates()
    reader = _reader_id(reader, labels, path)
    F["TRIAL_INDEX"] = F["TRIAL_INDEX"].astype(int)
    if messages is not None:
        msg = messages if isinstance(messages, pd.DataFrame) else read_messages(messages, encoding=encoding)
        win = trial_windows(msg, onset, end)
    else:
        win = pd.DataFrame({"trial": F["TRIAL_INDEX"].unique(), "onset": 0.0, "end": np.nan})
    F = F.merge(win, left_on="TRIAL_INDEX", right_on="trial", how="inner")
    out = pd.DataFrame({
        "reader": reader,
        "trial": F["TRIAL_INDEX"].to_numpy(int),
        "start": (F["CURRENT_FIX_START"] - F["onset"]).to_numpy(float),
        "end": (F["CURRENT_FIX_END"] - F["onset"]).to_numpy(float),
        "duration": F["CURRENT_FIX_DURATION"].to_numpy(float),
        "x": F["CURRENT_FIX_X"].to_numpy(float),
        "y": F["CURRENT_FIX_Y"].to_numpy(float),
        "pupil": F["CURRENT_FIX_PUPIL"].to_numpy(float) if "CURRENT_FIX_PUPIL" in F.columns else np.nan,
        "blink_around": F["CURRENT_FIX_BLINK_AROUND"].astype(str).str.strip().str.upper().to_numpy()
        if "CURRENT_FIX_BLINK_AROUND" in F.columns else "NONE",
        "ia": F["CURRENT_FIX_INTEREST_AREA_ID"].to_numpy(float) if "CURRENT_FIX_INTEREST_AREA_ID" in F.columns else np.nan,
    })
    out = _apply_design(out, read_design(design), reader)
    cols = ["reader", "item", "trial", "version", "start", "end", "duration", "x", "y", "pupil", "blink_around", "ia"]
    out = out[cols].sort_values(["trial", "start"], kind="mergesort").reset_index(drop=True)
    out.attrs = {"source": str(path)}
    return out


def read_csv(path: PathLike, columns: Mapping[str, str], hz: Optional[float] = None, missing=0, sep: str = ",",
             reader: Optional[str] = None, design=None, onset=None, pupil_unit: str = "diameter",
             blink_codes: Optional[Callable] = None) -> pd.DataFrame:
    """Read any sample-level file with a column mapping (in the spirit of gazeR's ``make_gazer()``).

    Parameters
    ----------
    path : str or path
        A delimited text file with one row per sample.
    columns : dict
        Maps our column names to the file's: ``time`` and ``pupil`` are required; ``reader``, ``trial`` (or ``item``),
        ``version``, ``eye``, ``gaze_x``, ``gaze_y``, ``in_blink``, ``in_saccade`` and ``trial_end`` are optional. A
        missing ``trial_end`` is set to the last sample of the trial.
    hz : float, optional
        Sampling rate; estimated from the time stamps if omitted.
    missing : number or list
        Value(s) that code missing pupil size, set to NaN (for example 0 or -1).
    onset : str or float, optional
        If ``time`` is not yet relative to text onset, a column giving the onset time of each trial (same unit) or a
        constant to subtract.
    pupil_unit : {"area", "diameter"}
        Unit of the pupil column, stored in ``attrs['pupil_unit']``.
    blink_codes : callable, optional
        Function mapping the raw ``in_blink`` column to booleans (default: values >= 1 or True).

    Returns
    -------
    DataFrame
        The sample table, sorted by reader, trial and time.
    """
    if "time" not in columns or "pupil" not in columns:
        raise ValueError("read_csv: 'columns' must map at least 'time' and 'pupil'")
    usecols = list(dict.fromkeys(list(columns.values()) + ([onset] if isinstance(onset, str) else [])))
    df = pd.read_csv(path, sep=sep, usecols=usecols, low_memory=False)
    out = pd.DataFrame(index=df.index)
    for ours, theirs in columns.items():
        out[ours] = df[theirs]
    if isinstance(onset, str):
        out["time"] = out["time"].astype(float) - df[onset].astype(float)
    elif onset is not None:
        out["time"] = out["time"].astype(float) - float(onset)
    out["reader"] = out["reader"].astype(str) if "reader" in out.columns else (
        str(reader) if reader is not None else os.path.splitext(os.path.basename(str(path)))[0])
    if "trial" not in out.columns:
        out["trial"] = out["item"] if "item" in out.columns else 1
    pupil = pd.to_numeric(out["pupil"], errors="coerce").astype(float)
    for code in np.atleast_1d(missing):
        pupil[pupil == code] = np.nan
    out["pupil"] = pupil
    for c in ("gaze_x", "gaze_y"):
        out[c] = pd.to_numeric(out[c], errors="coerce").astype(float) if c in out.columns else np.nan
    for c in ("in_blink", "in_saccade"):
        if c in out.columns:
            v = out[c]
            out[c] = blink_codes(v) if (blink_codes and c == "in_blink") else (pd.to_numeric(v, errors="coerce").fillna(0) >= 1)
        else:
            out[c] = False
    out["eye"] = out["eye"].astype(str).str.lower() if "eye" in out.columns else "unknown"
    out["time"] = out["time"].astype(float)
    if "trial_end" not in out.columns:
        out["trial_end"] = out.groupby(["reader", "trial"])["time"].transform("max")
    if design is not None:
        base = out.drop(columns=[c for c in ("item", "version") if c in out.columns])
        parts = [_apply_design(g.copy(), read_design(design), r) for r, g in base.groupby("reader", sort=False)]
        out = pd.concat(parts, ignore_index=True)
    else:
        if "item" not in out.columns:
            out["item"] = out["trial"]
        if "version" not in out.columns:
            out["version"] = np.nan
    out = out[SAMPLE_COLUMNS]
    out.attrs = {"pupil_unit": pupil_unit, "source": str(path), "tracker": "generic"}
    out = sort_trials(out)
    dup = out.duplicated(["reader", "trial", "time"])
    if dup.any():
        warnings.warn(f"read_csv: {path}: dropped {int(dup.sum()):,} samples that repeat the reader, trial and time of an "
                      "earlier sample")
        out = copy_attrs(out, out[~dup.to_numpy()].reset_index(drop=True))
    out.attrs["hz"] = float(hz) if hz else sampling_rate(out)
    return out


def to_diameter(data: pd.DataFrame, column: str = "pupil") -> pd.DataFrame:
    """Square root of pupil area, for analyses on the diameter scale (Section 3.3).

    Applied to bins (as in the paper, the square root of each 20 ms bin mean) or to samples. Columns ``pupil``,
    ``pupil_interp`` and ``pupil_corrected`` are transformed if present; ``attrs['pupil_unit']`` becomes "diameter".
    """
    if (data.attrs or {}).get("pupil_unit") == "diameter":
        raise ValueError("to_diameter: the data are already on the diameter scale")
    out = data.copy()
    for c in {column, "pupil_interp", "pupil_corrected", "pupil_raw"} & set(out.columns):
        out[c] = np.sqrt(out[c].astype(float))
    return copy_attrs(data, out, pupil_unit="diameter")
