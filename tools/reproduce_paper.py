#!/usr/bin/env python3
"""Reproduce the numbers of the tutorial (Tables 3 and S1 and the text) with pupilread, from the raw EyeLink reports.

Stage 1, on the machine that holds the raw Data Viewer reports (about 20 s per reader, 2 GB of memory):

    python tools/reproduce_paper.py prepare --data "Full study results" --cache cache

Stage 2, on a machine with R (lme4, mgcv); the time-course models need about 6 GB of memory and 30 minutes:

    python tools/reproduce_paper.py analyse --cache cache --out reproduction [--gamm] [--kcheck] [--old OLD]

Stage 2 adds the study's local text density (from the interest-area reports copied in stage 1), runs the package's
pooled stages, writes the trial table and binned trace (reproduction/for_R), fits Tables 3 and S1 with the package's
R scripts, recomputes the numbers quoted in the text and compares them with the values printed in the paper. With
--old (the folder of the original scripts' per_reader/ and results/), it also compares every trial value and every
20 ms bin with the outputs of the original scripts.

Everything study-specific is in this file: the reader list, the reading sets and their version order, the exclusions
of skimmed texts, the display (20.7 px per degree) and the text layout behind local text density.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
import pupilread as pr  # noqa: E402

READERS = ("01 02 03 04 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 24 25 26 28 29 30 31 32 33 35 36 37 38 39 40 "
           "41 42 43 44 45 46 48 49 50").split()
SET1 = "01 02 07 08 10 12 14 16 18 20 25 27 29 31 33 35 38 39 41 43 45 47 49".split()
IA_READERS = {"Set 1": ("01", "02"), "Set 2": ("03", "04")}   # layout from the first, checked against the second
PX_PER_DEGREE = 20.7
N_ITEMS = 24


def reading_set(r: str) -> str:
    return "Set 1" if r in SET1 else "Set 2"


def version_of(r: str, item: int) -> str:
    """Set 1 read the odd-numbered texts simplified, Set 2 the even-numbered ones."""
    odd = item % 2 == 1
    simplified = odd if reading_set(r) == "Set 1" else not odd
    return "simplified" if simplified else "non-simplified"


def study_files(data: str, r: str) -> dict:
    folder = os.path.join(data, "SET 1" if r in SET1 else "SET 2", r, "Output")

    def find(key):
        c = sorted(f for f in os.listdir(folder) if not f.startswith("._") and key in f.lower())
        return os.path.join(folder, c[0])
    return {"samples": find("sample"), "messages": find("mess"), "fixations": find("fixation"),
            "ia": find("interest area")}


def design_table() -> pd.DataFrame:
    rows = [(r, i, i, version_of(r, i), reading_set(r)) for r in READERS for i in range(1, N_ITEMS + 1)]
    return pd.DataFrame(rows, columns=["reader", "trial", "item", "version", "reading_set"])


SCREEN = {"too_fast_wpm": 600, "coverage_floor": 0.50, "short_fix_ms": 150, "reached_floor": 0.60}


def _screen_reader(ia_path: str, mean_fix: pd.Series) -> pd.DataFrame:
    """The four trial flags of the screen for skimmed or incomplete reading, from one interest-area report.

    The same computation as the companion study's screen: reading rate (words per minute of trial dwell time), share of
    words of five or more characters that were fixated, mean fixation duration (``mean_fix``, per trial) and how far
    into the text the last fixated word lies. Repeated rows of the report are dropped first.
    """
    d = pd.read_csv(ia_path, sep="\t", low_memory=False)
    d.columns = [c.replace("\ufeff", "").strip() for c in d.columns]
    d = d.drop_duplicates()
    d["TRIAL_INDEX"] = pd.to_numeric(d["TRIAL_INDEX"], errors="coerce")
    d = d.dropna(subset=["TRIAL_INDEX"])
    d["TRIAL_INDEX"] = d["TRIAL_INDEX"].astype(int)
    for c in ("IA_DWELL_TIME", "IA_FIXATION_COUNT", "TRIAL_DWELL_TIME", "IA_ID"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["is_word"] = d["IA_LABEL"].apply(lambda x: isinstance(x, str) and any(ch.isalnum() for ch in x))
    d["word_len"] = d["IA_LABEL"].astype(str).str.strip().str.len().where(d["is_word"])
    rows = []
    for ti, g in d.groupby("TRIAL_INDEX"):
        w = g[g["is_word"]]
        if not len(w):
            continue
        fixated = w["IA_FIXATION_COUNT"].fillna(0) > 0
        dw = g["TRIAL_DWELL_TIME"].dropna()
        dwell = float(dw.iloc[0]) if len(dw) else float(g["IA_DWELL_TIME"].sum())
        lw = w[w["word_len"] >= 5]
        cov = float((lw["IA_FIXATION_COUNT"].fillna(0) > 0).mean()) if len(lw) else np.nan
        reached = float(w.loc[fixated, "IA_ID"].max() / w["IA_ID"].max()) if fixated.any() else 0.0
        rows.append((ti, len(w) / (dwell / 60000.0) if dwell > 0 else np.inf, cov, reached))
    T = pd.DataFrame(rows, columns=["TRIAL_INDEX", "reading_rate_wpm", "coverage_longwords", "prop_text_reached"])
    T["mean_fix_dur_ms"] = T["TRIAL_INDEX"].map(mean_fix)
    T["flagged"] = ((T["reading_rate_wpm"] > SCREEN["too_fast_wpm"]) | (T["coverage_longwords"] < SCREEN["coverage_floor"])
                    | (T["mean_fix_dur_ms"] < SCREEN["short_fix_ms"]) | (T["prop_text_reached"] < SCREEN["reached_floor"]))
    return T


def exclusions(data: str, legacy: bool = False) -> pd.DataFrame:
    """Trials excluded before preprocessing, blind to version, as skimmed or incomplete (four criteria).

    The flags come from the companion study's screen (``full_study_trial_validity.csv``). That screen read reader 42's
    interest-area report, which lists every row twice, so it counted the reader's words twice and doubled the reading
    rate; five of the reader's trials crossed the 600 words-per-minute ceiling only for that reason. For every reader
    whose report repeats rows, the flags are therefore recomputed here from the report without the repeats (with
    ``legacy``, the screen's flags are used as they are, as in the original analysis).
    """
    V = pd.read_csv(os.path.join(data, "RUN_IN_R", "data", "full_study_trial_validity.csv"))
    V["reader"] = V["participant"].astype(int).map("{:02d}".format)
    V["flag"] = V["flagged"].astype(str).isin(["True", "TRUE", "1", "1.0"])
    notes = []
    if not legacy:
        for r in READERS:
            ia = study_files(data, r)["ia"]
            raw = pd.read_csv(ia, sep="\t", low_memory=False,
                              usecols=lambda c: c.replace("\ufeff", "").strip() in ("TRIAL_INDEX", "IA_ID"))
            if not raw.duplicated().any():
                continue
            m = V["reader"] == r
            new = _screen_reader(ia, V.loc[m].set_index("TRIAL_INDEX")["mean_fix_dur_ms"])
            flag = V.loc[m, "TRIAL_INDEX"].map(new.set_index("TRIAL_INDEX")["flagged"]).fillna(False).astype(bool)
            changed = sorted(int(t) for t, a, b in zip(V.loc[m, "TRIAL_INDEX"], V.loc[m, "flag"], flag) if a != b)
            V.loc[m, "flag"] = flag
            notes.append(f"reader {r}: interest-area report repeats rows; screen recomputed without them, "
                         f"flags changed for trials {changed}")
    for n in notes:
        print(n, flush=True)
    V = V[V["flag"]]
    return pd.DataFrame({"reader": V["reader"], "trial": V["TRIAL_INDEX"].astype(int), "reason": "skimmed or incomplete"})


def study_config(cache: str, data: str = None) -> dict:
    cfg = {"data": {"design": os.path.join(cache, "design.csv"), "exclude": os.path.join(cache, "exclusions.csv")},
           "display": {"px_per_degree": PX_PER_DEGREE}}
    if data:
        cfg["data"]["readers"] = {r: {k: v for k, v in study_files(data, r).items() if k != "ia"} for r in READERS}
    return cfg


# --------------------------------------------------------------------------------------------- stage 1: prepare

def legacy_mode():
    """Impose three assumptions of the original scripts, to show that the package reproduces them exactly.

    1. Every recording was treated as 1,000 Hz: blink padding, the interpolation limit and the blink-locked lags were
       counted in samples, so recordings at 2,000 Hz got 50 ms padding (and 25% valid samples sufficed for a 20 ms bin).
    2. Blink padding summed the blink flags in 8-bit integers, which overflow wherever more than 127 of the 201 samples
       centred on a sample lie in blinks, so the middle of long blinks (where the pupil is missing) and short gaps
       between blinks (where it is valid) were left unflagged.
    3. Duplicated rows of a sample report (one reader's report lists every sample twice) were kept.

    The exclusion list then also keeps the screen's flags for that reader (see :func:`exclusions`).
    """
    import pupilread._utils as U
    import pupilread.blinks as Bk

    def dilate_int8(mask, k):
        m = np.asarray(mask, bool)
        if k <= 0 or not m.any():
            return m.copy()
        return np.convolve(m.astype(np.int8), np.ones(2 * k + 1, np.int8), mode="same") > 0
    U.dilate = dilate_int8
    Bk.dilate = dilate_int8


def _restrict(df, keys):
    k = pd.MultiIndex.from_frame(keys[["reader", "trial"]].astype(str))
    return df[pd.MultiIndex.from_arrays([df["reader"].astype(str), df["trial"].astype(str)]).isin(k)].reset_index(drop=True)


def cmd_prepare(a):
    os.makedirs(a.cache, exist_ok=True)
    design_table().to_csv(os.path.join(a.cache, "design.csv"), index=False)
    exclusions(a.data, legacy=a.legacy).to_csv(os.path.join(a.cache, "exclusions.csv"), index=False)
    ia = os.path.join(a.cache, "ia")
    os.makedirs(ia, exist_ok=True)
    for s, rr in IA_READERS.items():
        for r in rr:
            dst = os.path.join(ia, f"{r}.txt")
            if not os.path.exists(dst):
                shutil.copyfile(study_files(a.data, r)["ia"], dst)
    cfg = pr.load_config(study_config(a.cache, a.data))
    if a.legacy:
        legacy_mode()
        cfg["data"]["drop_duplicates"] = False
    t_all = time.time()
    for r in (a.readers.split(",") if a.readers else READERS):
        folder = os.path.join(a.cache, r)
        if os.path.exists(os.path.join(folder, "done.json")) and not a.force:
            continue
        if a.max_seconds and time.time() - t_all > a.max_seconds:
            print("time limit reached; run the same command again to continue", flush=True)
            return
        t0 = time.time()
        job = dict(reader=r, **cfg["data"]["readers"][r])
        s, f = pr.read_reader(job, cfg)
        hz = s.attrs.get("hz")
        if a.legacy:
            s.attrs["hz"] = 1000.0
        p = pr.prepare(s, f, cfg)
        p.save(folder)
        # checks of the paper that need samples: blink-locked traces over all trials (as Figure 2D) and the
        # agreement of pupil-based blink detection with EyeLink blinks over the kept trials (Note S1)
        sp = pr.pad_blinks(s)
        del s
        rm = pr.reader_means(p.bins)
        pr.event_response(sp, "blink", window=(-200, 2000), by="version", means=rm).by_reader.to_csv(
            os.path.join(folder, "blink_events_all_trials.csv.gz"), index=False)
        sk = _restrict(sp, p.trials.loc[~p.trials["excluded"], ["reader", "trial"]])
        del sp
        pr.detector_agreement(sk).to_csv(os.path.join(folder, "detector_agreement.csv"), index=False)
        with open(os.path.join(folder, "done.json"), "w") as fh:
            json.dump({"reader": r, "samples_kept": int(len(sk)), "hz": hz, "legacy": bool(a.legacy),
                       "seconds": round(time.time() - t0, 1), "pupilread": pr.__version__}, fh)
        print(f"reader {r}: {len(p.trials)} trials, {int(p.trials['excluded'].sum())} excluded, "
              f"{time.time() - t0:.0f} s", flush=True)
        del p, sk, f


# --------------------------------------------------------------------------------------------- local text density

FOV, PARA = 21, 104          # half-widths (px) of the foveal and parafoveal squares (1 and 5 degrees)
SPACE, CHAR = 0.278 * 20, 10.0


def _ia(path):
    d = pd.read_csv(path, sep="\t", encoding="utf-8-sig", low_memory=False,
                    usecols=lambda c: c.replace("﻿", "") in ["TRIAL_INDEX", "IA_ID", "IA_LABEL", "IA_LEFT", "IA_RIGHT",
                                                                  "IA_TOP", "IA_BOTTOM"])
    d.columns = [c.replace("﻿", "") for c in d.columns]
    d["IA_LABEL"] = d["IA_LABEL"].astype(str)
    return d


def _line_centres(d):
    L = d[["IA_TOP", "IA_BOTTOM"]].drop_duplicates().sort_values("IA_TOP").reset_index(drop=True)
    h = L.IA_BOTTOM - L.IA_TOP
    k0 = int((h - h.median()).abs().idxmin())
    c = {k0: (L.IA_TOP[k0] + L.IA_BOTTOM[k0]) / 2}
    for k in range(k0 - 1, -1, -1):
        c[k] = 2 * L.IA_TOP[k + 1] - c[k + 1]
    for k in range(k0 + 1, len(L)):
        c[k] = 2 * L.IA_BOTTOM[k - 1] - c[k - 1]
    c = {k: c[k0] + 48 * round((v - c[k0]) / 48) for k, v in c.items()}
    return {L.IA_TOP[k]: c[k] for k in c}


def _ink_boxes(d):
    """Boxes of printed letters: interest areas trimmed to the word, around the line centres (20-point text)."""
    cen = _line_centres(d)
    first_top = min(cen)
    out = []
    for r in d.itertuples():
        yc = cen[r.IA_TOP]
        hh = 12 if r.IA_TOP == first_top else 10
        right = r.IA_RIGHT - SPACE
        left = max(r.IA_LEFT, right - CHAR * len(r.IA_LABEL))
        if right > left:
            out.append((left, right, yc - hh, yc + hh))
    return np.array(out)


def _cover(boxes, x, y, w):
    """Share of the square [x - w, x + w] x [y - w, y + w] covered by the boxes."""
    l, r, t, b = (boxes[:, i][None, :] for i in range(4))
    ox = np.clip(np.minimum(r, x[:, None] + w) - np.maximum(l, x[:, None] - w), 0, None)
    oy = np.clip(np.minimum(b, y[:, None] + w) - np.maximum(t, y[:, None] - w), 0, None)
    return (ox * oy).sum(1) / (2 * w) ** 2


def layouts(ia_folder):
    boxes, same = {}, {}
    for s, (r1, r2) in IA_READERS.items():
        d1, d2 = _ia(os.path.join(ia_folder, f"{r1}.txt")), _ia(os.path.join(ia_folder, f"{r2}.txt"))
        for item, g in d1.groupby("TRIAL_INDEX"):
            boxes[(s, int(item))] = _ink_boxes(g)
        same[s] = all(np.allclose(_ink_boxes(g), boxes[(s, int(i))]) for i, g in d2.groupby("TRIAL_INDEX"))
    return boxes, same


def add_ink(bins, ia_folder, window=(500, 20000)):
    """Local text density at the gaze position of each valid 20 ms bin in ``window`` (foveal and parafoveal)."""
    boxes, same = layouts(ia_folder)
    ok = pr._utils.ok_mask(bins)
    t = bins["time"].to_numpy(float)
    m = ok & (t >= window[0]) & (t < window[1]) & np.isfinite(bins["gaze_x"].to_numpy(float)) & np.isfinite(bins["gaze_y"].to_numpy(float))
    fov = np.full(len(bins), np.nan)
    para = np.full(len(bins), np.nan)
    sets = bins["reader"].astype(str).map(reading_set).to_numpy()
    items = bins["item"].to_numpy(int)
    x, y = bins["gaze_x"].to_numpy(float), bins["gaze_y"].to_numpy(float)
    idx = np.flatnonzero(m)
    key = pd.Series(list(zip(sets[idx], items[idx])), index=idx)
    for k, ii in key.groupby(key).groups.items():
        bx = boxes[k]
        ii = np.asarray(ii)
        for c0 in range(0, len(ii), 20000):
            jj = ii[c0:c0 + 20000]
            fov[jj] = _cover(bx, x[jj], y[jj], FOV)
            para[jj] = _cover(bx, x[jj], y[jj], PARA)
    bins["ink_fovea"] = fov
    bins["ink_parafovea"] = para
    return same


# --------------------------------------------------------------------------------------------- stage 2: analyse

#: Values of the first full-study draft, from the original scripts; ``prepare --legacy`` reproduces them exactly.
#: (estimate, lo, hi, p) for models, (value, decimals) or ("about", value, tolerance) for single numbers.
ORIGINAL_TABLE3 = {
    "change_0_20s": (1.27, -0.28, 2.83, .108), "fixations": (1.32, -0.36, 3.00, .124),
    "valid_75": (1.53, -0.03, 3.10, .054), "baseline_0_500": (1.45, 0.06, 2.83, .041),
    "low_baselines_kept": (1.03, -0.56, 2.62, .204), "no_baseline": (1.39, 0.51, 2.28, .002),
    "baseline_covariate": (1.36, 0.51, 2.20, .002), "diameter": (0.67, -0.07, 1.42, .078),
    "whole_trial": (1.58, 0.04, 3.12, .045), "random_intercepts": (1.26, -0.16, 2.68, .082),
    "control_predictors": (0.81, -0.73, 2.34, .303), "gaze_regression": (1.16, -0.55, 2.87, .184),
    "gaze_steps_eye": (1.75, -0.03, 3.52, .054), "gaze_steps_type": (0.54, -1.02, 2.09, .499),
    "GAMM M0 naive": (1.22, 1.09, 1.35, None), "GAMM M1 no gaze term": (1.23, -0.29, 2.76, .113),
    "GAMM M2 gaze surface": (2.04, 0.51, 3.58, .009),
}
ORIGINAL_TABLE_S1 = {
    "fixations_same_trials": (1.38, -0.27, 3.03, .101), "interpolated": (1.27, -0.28, 2.83, .108),
    "window_2_20": (1.40, -0.19, 2.99, .084),
    "window_3_20": (1.47, -0.13, 3.08, .072), "window_5_20": (1.40, -0.22, 3.02, .090),
    "left_eye": (1.41, -0.88, 3.70, .228), "right_eye": (1.27, -0.80, 3.34, .228),
    "whole_trial_covariates": (1.57, 0.02, 3.13, .047), "cut_1s": (1.28, -0.28, 2.83, .107),
    "cut_2s": (1.27, -0.28, 2.82, .108), "gaze_regression_time": (1.14, -0.55, 2.83, .185),
    "gaze_steps_reader": (0.80, -1.28, 2.89, .450), "gaze_steps_map": (0.84, -0.78, 2.45, .310),
    "GAMM M1 without AR1": (1.24, -0.33, 2.82, .122), "GAMM M2 without AR1": (0.79, -0.77, 2.36, .320),
}
ORIGINAL_N_TRIALS = {"default": 982, "fixations": 919, "fixations_same_trials": 919, "valid_75": 927, "low_baselines_kept": 984,
            "left_eye": 477, "right_eye": 505}
ORIGINAL_TEXT = {  # name: (value printed, decimals)
    "3.1 fixation pupil vs samples, r (> .9999)": (0.9999, 4),
    "3.1 retained fixations cover reading time (%)": (73, 0),
    "3.2 samples lost (%)": (9.9, 1), "3.2 invalid (%)": (4.1, 1), "3.2 lost to blink padding (%)": (5.8, 1),
    "3.2 trials with < 50% valid samples": (12, 0), "3.2 of them non-simplified": (5, 0), "3.2 of them simplified": (7, 0),
    "3.3 trials without a 0-200 ms baseline": (18, 0), "3.3 trials without a 0-500 ms baseline": (8, 0),
    "3.3 low baselines (< 60%)": (2, 0), "3.3 low baselines that were non-simplified": (2, 0),
    "3.3 analysed trials": (982, 0),
    "3.3 baseline difference, 0-200 ms (%)": (-0.11, 2), "3.3 baseline difference, 0-500 ms (%)": (-0.18, 2),
    "3.3 onset: time of the first rise (ms, about)": (200, -2), "3.3 onset: time of the minimum (ms, about)": (700, -2),
    "3.3 onset: second peak (s, 1.5-2)": ("range", 1.5, 2.0),
    "3.4 gaze shift, simplified minus non-simplified, x (px, about -80)": (-80, -1),
    "3.4 gaze shift, simplified minus non-simplified, y (px, about 40)": (40, -1),
    "3.4 return-sweep step, left eye (%)": (6.5, 1), "3.4 return-sweep step, right eye (%)": (2.9, 1),
    "3.5 trial duration, non-simplified (s)": (43.2, 1), "3.5 trial duration, simplified (s)": (38.5, 1),
    "3.5 trials ending before 20 s": (76, 0), "3.5 of them simplified": (45, 0),
    "3.5 rise in the last second before the key press (%)": (5.0, 1),
    "3.5 rise, non-simplified minus simplified, p": (0.005, 3),
    "3.5 blink response: largest rise, mean of versions (%)": ("about", 3.0, 0.5),
    "3.5 blink response: lowest point, mean of versions (%)": ("about", -3.0, 0.5),
    "3.5 blink rate, non-simplified (per s)": (0.32, 2), "3.5 blink rate, simplified (per s)": (0.33, 2),
    "3.5 saccade rate, non-simplified (per s)": (3.51, 2), "3.5 saccade rate, simplified (per s)": (3.52, 2),
    "3.6 trials excluded as skimmed or incomplete": (66, 0), "3.6 trials read": (1080, 0),
    "3.6 grand mean: median difference from 3 s (percentage points)": (1.5, 1),
    "3.7 fixations from 0.5 to 20 s": (54033, 0), "3.7 fixation-level t": (11.06, 2),
    "3.7 paired t-test on reader means, p": (0.088, 3),
    "3.7 control predictors, no adjustment on the same bins (%)": (1.25, 2),
    "3.7 control predictors, all (%)": (0.81, 2),
    "3.7 text density changed the estimate by (percentage points)": (0.06, 2),
    "3.7 GAMM rho (AR1)": (0.92, 2), "3.7 GAMM M0 residual lag-1": (0.98, 2), "3.7 GAMM M1 AR1 residual lag-1": ("about", 0.23, 0.006),  # the draft rounded the log's 0.225 to .23
    "4.4 d_z across readers": (0.26, 2), "4.4 readers for 80% power": (118, 0), "4.4 readers for 80% power at d_z = 0.3": (89, 0),
    "S1 detector flags inside padded blinks, median (%)": (91.9, 1), "S1 detector flags outside padded blinks, median (%)": (2.1, 1),
    "S1 trials kept after the exclusions for skimming and missing data": (1002, 0),
    "S2 rho without gaze surface": (0.917, 3), "S2 rho with gaze surface": (0.918, 3),
    "S2 excess kurtosis without gaze surface": (58, 0), "S2 excess kurtosis with gaze surface": (28, 0),
    "S2 k-check readers": (23, 0), "S2 k-check trials": (488, 0),
    "S2 k-check, k = 3: estimate (%)": (2.27, 2), "S2 k-check, k = 3: lower (%)": (0.26, 2), "S2 k-check, k = 3: upper (%)": (4.28, 2),
    "S2 k-check, k = 5: estimate (%)": (2.25, 2), "S2 k-check, k = 5: lower (%)": (0.23, 2), "S2 k-check, k = 5: upper (%)": (4.27, 2),
    "5 smallest estimate in Table 3 (%)": (0.54, 2), "5 largest estimate in Table 3 (%)": (2.04, 2),
}

#: Values printed in the paper (Table 3, Table S1, text), from pupilread 1.0.0 with its defaults.
TABLE3 = {
    "change_0_20s": (1.37, -0.20, 2.94, .087), "fixations": (1.38, -0.31, 3.07, .110),
    "valid_75": (1.58, 0.00, 3.16, .049), "baseline_0_500": (1.51, 0.12, 2.90, .033),
    "low_baselines_kept": (1.13, -0.48, 2.74, .168), "no_baseline": (1.36, 0.48, 2.25, .003),
    "baseline_covariate": (1.36, 0.51, 2.20, .002), "diameter": (0.71, -0.04, 1.47, .063),
    "whole_trial": (1.67, 0.11, 3.23, .036), "random_intercepts": (1.35, -0.07, 2.78, .062),
    "control_predictors": (0.89, -0.67, 2.44, .263), "gaze_regression": (1.26, -0.48, 2.99, .155),
    "gaze_steps_eye": (1.85, 0.06, 3.63, .042), "gaze_steps_type": (0.63, -0.94, 2.19, .434),
    "GAMM M0 naive": (1.29, 1.16, 1.42, None), "GAMM M1 no gaze term": (1.33, -0.22, 2.87, .092),
    "GAMM M2 gaze surface": (1.96, 0.40, 3.52, .014),
}
TABLE_S1 = {
    "fixations_same_trials": (1.45, -0.22, 3.11, .088), "interpolated": (1.37, -0.20, 2.94, .087),
    "window_2_20": (1.49, -0.12, 3.10, .069),
    "window_3_20": (1.55, -0.06, 3.17, .060), "window_5_20": (1.47, -0.15, 3.10, .076),
    "left_eye": (1.41, -0.88, 3.70, .228), "right_eye": (1.43, -0.67, 3.53, .183),
    "whole_trial_covariates": (1.66, 0.08, 3.23, .039), "cut_1s": (1.37, -0.20, 2.94, .087),
    "cut_2s": (1.37, -0.20, 2.93, .087), "gaze_regression_time": (1.23, -0.47, 2.94, .156),
    "gaze_steps_reader": (0.91, -1.19, 3.00, .396), "gaze_steps_map": (0.93, -0.69, 2.56, .261),
    "GAMM M1 without AR1": (1.34, -0.26, 2.94, .100), "GAMM M2 without AR1": (0.85, -0.56, 2.26, .237),
}
N_TRIALS = {"default": 986, "fixations": 924, "fixations_same_trials": 924, "valid_75": 930, "low_baselines_kept": 988,
            "left_eye": 477, "right_eye": 509}
TEXT = dict(ORIGINAL_TEXT)
TEXT.update({
    "3.2 samples lost (%)": (10.1, 1), "3.2 lost to blink padding (%)": (6.0, 1),
    "3.3 trials without a 0-200 ms baseline": (19, 0), "3.3 trials without a 0-500 ms baseline": (9, 0),
    "3.3 analysed trials": (986, 0),
    "3.3 baseline difference, 0-200 ms (%)": (-0.14, 2), "3.3 baseline difference, 0-200 ms: lower (%)": (-1.99, 2),
    "3.3 baseline difference, 0-200 ms: upper (%)": (1.71, 2),
    "3.3 baseline difference, 0-500 ms (%)": (-0.19, 2), "3.3 baseline difference, 0-500 ms: lower (%)": (-1.77, 2),
    "3.3 baseline difference, 0-500 ms: upper (%)": (1.38, 2),
    "3.5 trials ending before 20 s": (77, 0), "3.5 of them simplified": (46, 0),
    "3.5 rise in the last second before the key press (%)": (5.1, 1),
    "3.5 rise, non-simplified minus simplified, p": (0.005, 3),
    "3.5 blink response: largest rise, mean of versions (%)": ("about", 3.5, 0.25),
    "3.5 blink response: lowest point, mean of versions (%)": ("about", -3.5, 0.25),
    "3.5 blink rate, simplified (per s)": (0.32, 2),
    "3.6 trials excluded as skimmed or incomplete": (61, 0),
    "3.6 grand mean: median difference from 3 s (percentage points)": (1.6, 1),
    "3.7 fixations from 0.5 to 20 s": (54227, 0), "3.7 fixation-level t": (11.60, 2),
    "3.7 paired t-test on reader means, p": (0.080, 3),
    "3.7 control predictors, no adjustment on the same bins (%)": (1.35, 2),
    "3.7 control predictors, all (%)": (0.89, 2),
    "3.7 text density changed the estimate by (percentage points)": (0.05, 2),
    "3.7 GAMM M1 AR1 residual lag-1": (0.27, 2),
    "4.4 d_z across readers": (0.267, 3), "4.4 readers for 80% power": (113, 0),
    "4.4 readers for 80% power at d_z = 0.3": (90, 0),
    "S1 detector flags inside padded blinks, median (%)": (92.8, 1),
    "S1 detector flags outside padded blinks, median (%)": (2.3, 1),
    "S1 trials kept after the exclusions for skimming and missing data": (1007, 0),
    "S2 rho without gaze surface": (0.922, 3), "S2 rho with gaze surface": (0.920, 3),
    "S2 excess kurtosis without gaze surface": (53, 0), "S2 excess kurtosis with gaze surface": (29, 0),
    "S2 k-check trials": (487, 0),
    "S2 k-check, k = 3: estimate (%)": (2.31, 2), "S2 k-check, k = 3: lower (%)": (0.30, 2), "S2 k-check, k = 3: upper (%)": (4.33, 2),
    "S2 k-check, k = 5: estimate (%)": (2.29, 2), "S2 k-check, k = 5: lower (%)": (0.27, 2), "S2 k-check, k = 5: upper (%)": (4.31, 2),
    "5 smallest estimate in Table 3 (%)": (0.63, 2), "5 largest estimate in Table 3 (%)": (1.96, 2),
})


def _paired(m: pd.DataFrame, a="simplified", b="non-simplified"):
    from scipy import stats
    d = (m[a] - m[b]).dropna()
    t, p = stats.ttest_1samp(d, 0)
    h = stats.t.ppf(0.975, len(d) - 1) * d.std(ddof=1) / math.sqrt(len(d))
    return dict(diff=d.mean(), lo=d.mean() - h, hi=d.mean() + h, t=t, p=p, n=len(d), dz=d.mean() / d.std(ddof=1),
                n_pos=int((d > 0).sum()))


def _by_reader(df, col, by="version"):
    return df.groupby(["reader", by])[col].mean().unstack(by)


#: Readers needed for a given power are rounded up, from d_z as printed (three decimals), so that the printed numbers
#: check against each other; the first draft used the unrounded d_z and rounded to the nearest reader (legacy mode).
ROUND_UP = True


def _power(dz, power=0.8):
    """Readers needed for a paired, two-sided t-test at alpha = .05 to reach ``power`` for a standardised effect dz."""
    try:
        from statsmodels.stats.power import TTestPower
        return float(TTestPower().solve_power(effect_size=dz, power=power, alpha=0.05, alternative="two-sided"))
    except ImportError:
        from scipy import stats, optimize

        def f(n):
            c = stats.t.ppf(0.975, n - 1)
            nc = dz * math.sqrt(n)
            return stats.nct.sf(c, n - 1, nc) + stats.nct.cdf(-c, n - 1, nc) - power
        return optimize.brentq(f, 2.5, 400)


def text_numbers(res, data, T, cache, gamm=None):
    """The numbers quoted in the text, recomputed from the package's outputs."""
    out = {}
    D = data.trials
    kept = D[~D["excluded"]]
    an = T[T["baseline_pct"] >= 60]
    # 3.1
    lv = data.levels
    akey = pd.MultiIndex.from_frame(an[["reader", "trial"]].astype(str))
    la = lv[pd.MultiIndex.from_arrays([lv["reader"].astype(str), lv["trial"].astype(str)]).isin(akey)]
    ok = np.isfinite(la["pupil"]) & np.isfinite(la["pupil_samples"]) & (la["n_valid"] > 0)
    out["3.1 fixation pupil vs samples, r (> .9999)"] = float(np.corrcoef(la.loc[ok, "pupil"], la.loc[ok, "pupil_samples"])[0, 1])
    out["3.1 retained fixations cover reading time (%)"] = 100 * res.levels.get("coverage_mean", np.nan)
    # 3.2
    for c, name in (("pct_valid", "3.2 samples lost (%)"), ("pct_invalid", "3.2 invalid (%)"),
                    ("pct_blink_pad", "3.2 lost to blink padding (%)")):
        m = _by_reader(kept, c).mean()
        v = float(m.mean())
        out[name] = 100 - v if c == "pct_valid" else v
    listed = D["reason"] == "listed"
    low = D["reason"].str.startswith("valid")
    out["3.2 trials with < 50% valid samples"] = int(low.sum())
    out["3.2 of them non-simplified"] = int((low & (D["version"] == "non-simplified")).sum())
    out["3.2 of them simplified"] = int((low & (D["version"] == "simplified")).sum())
    # 3.3
    nk = int(len(kept))
    out["3.3 trials without a 0-200 ms baseline"] = nk - int(np.isfinite(T["baseline_pct"]).sum())
    b500 = pr.baseline(data.bins, window=(0, 500))
    lb500 = pr.low_baselines(b500)
    out["3.3 trials without a 0-500 ms baseline"] = nk - int(np.isfinite(lb500["baseline_pct"]).sum())
    lowb = T[T["baseline_pct"] < 60]
    out["3.3 low baselines (< 60%)"] = int(len(lowb))
    out["3.3 low baselines that were non-simplified"] = int((lowb["version"] == "non-simplified").sum())
    out["3.3 analysed trials"] = int(len(an))
    l5 = lb500.merge(an[["reader", "trial"]], on=["reader", "trial"])
    for wn, src in (("0-200", an), ("0-500", l5)):       # simplified minus non-simplified, mean of readers, 95% CI
        q = _paired(_by_reader(src, "baseline_pct"))
        out[f"3.3 baseline difference, {wn} ms (%)"] = q["diff"]
        out[f"3.3 baseline difference, {wn} ms: lower (%)"] = q["lo"]
        out[f"3.3 baseline difference, {wn} ms: upper (%)"] = q["hi"]
    bn = pr.baseline(data.bins, method="none")
    fig = pr.plot_grand_mean(bn, by=None, bin_s=0.1, max_s=5, min_readers=1, min_baseline_pct=None)
    gm = fig.grand_mean
    gm = gm.assign(ms=(gm["sec"] + 0.5) * 100)

    def at(lo, hi, fn):
        z = gm[(gm["ms"] >= lo) & (gm["ms"] < hi)]
        return float(z.loc[getattr(z["mean"], fn)(), "ms"]) if len(z) else np.nan
    out["3.3 onset: time of the first rise (ms, about)"] = at(0, 500, "idxmax")
    out["3.3 onset: time of the minimum (ms, about)"] = at(300, 1500, "idxmin")
    out["3.3 onset: second peak (s, 1.5-2)"] = at(1000, 3500, "idxmax") / 1000
    import matplotlib.pyplot as plt
    plt.close(fig)
    out["_first5s"] = gm
    # 3.4 gaze shift (window minus baseline, analysed trials)
    B = res.bins
    okb = pr._utils.ok_mask(B) & np.isfinite(B["gaze_x"]) & np.isfinite(B["gaze_y"])
    Bg = B[okb]
    key = ["reader", "trial"]
    w = Bg[(Bg["time"] >= 500) & (Bg["time"] < 20000)].groupby(key)[["gaze_x", "gaze_y"]].mean()
    b0 = Bg[Bg["time"] < 200].groupby(key)[["gaze_x", "gaze_y"]].mean()
    g = (w - b0).dropna().reset_index().merge(an[["reader", "trial", "version"]], on=key)
    out["3.4 gaze shift, simplified minus non-simplified, x (px, about -80)"] = _paired(_by_reader(g, "gaze_x"))["diff"]
    out["3.4 gaze shift, simplified minus non-simplified, y (px, about 40)"] = _paired(_by_reader(g, "gaze_y"))["diff"]
    st = res.steps
    rs = st[(st["type"] == "return sweep") & np.isfinite(st["step"])]
    m = rs.groupby(["eye", "reader"])["step"].mean().groupby("eye").mean()
    out["3.4 return-sweep step, left eye (%)"] = float(m.get("left", np.nan))
    out["3.4 return-sweep step, right eye (%)"] = float(m.get("right", np.nan))
    fw = st[(st["type"] == "forward") & np.isfinite(st["step"])]
    q = fw.groupby(["eye", "reader"])[["step", "late"]].mean().groupby("eye").mean()
    out["_forward_late_minus_step"] = (q["late"] - q["step"]).to_dict()
    # slopes: regression slopes in % of the reader mean, against the step slopes
    sl_t = pr.step_slopes(st, by="eye", method="by_type")
    sl_j = pr.step_slopes(st, by="eye", method="joint")
    rm = pr.reader_means(data.bins)
    out["_slopes"] = {"steps_joint": sl_j[["bX", "bY"]].to_dict("index"), "steps_by_type": sl_t[["bX", "bY"]].to_dict("index")}
    eye_of = data.trials.drop_duplicates("reader").set_index("reader")["eye"] if "eye" in data.trials.columns else None
    if eye_of is None:
        eye_of = data.bins.drop_duplicates("reader").set_index("reader")["eye"]
    for e in ("left", "right"):
        rr = [r for r in eye_of.index if eye_of[r] == e]
        sub = data.bins[data.bins["reader"].isin(rr)]
        s1 = pr.regression_slopes(sub, means=rm)
        erm = float(rm[rr].mean())
        out["_slopes"][f"regression_{e}_pct"] = {"bX": 100 * s1["bX"] / erm, "bY": 100 * s1["bY"] / erm}
    # 3.5
    dur = _by_reader(kept, "duration_s").mean()
    out["_duration_analysed"] = _by_reader(an, "duration_s").mean().to_dict()
    out["3.5 trial duration, non-simplified (s)"] = float(dur["non-simplified"])
    out["3.5 trial duration, simplified (s)"] = float(dur["simplified"])
    short = an[an["duration_s"] < 20]
    out["3.5 trials ending before 20 s"] = int(len(short))
    out["3.5 of them simplified"] = int((short["version"] == "simplified").sum())
    E = B[(B["duration"] >= 10000) & (B["time"] >= B["duration"] - 5000)].copy()
    E = E[pr._utils.ok_mask(E)]
    E["r"] = (np.floor((E["time"] - E["duration"]) / 100) * 100).astype(int)
    E = E[E["r"] >= -5000]
    ref = E[E["r"] < -4000].groupby(key)["pupil"].mean().rename("ref")
    E = E.join(ref, on=key)
    E["v"] = 100 * (E["pupil"] - E["ref"]) / E["reader"].map(rm)
    rise = E[E["r"] >= -1000].groupby(key)["v"].mean().rename("rise").reset_index().merge(
        data.trials[["reader", "trial", "version"]], on=key)
    mr = _by_reader(rise, "rise")
    out["3.5 rise in the last second before the key press (%)"] = float(mr.mean(axis=1).mean())
    out["3.5 rise, non-simplified minus simplified, p"] = _paired(mr, "non-simplified", "simplified")["p"]
    for c, nm in (("blink_rate", "blink rate"), ("saccade_rate", "saccade rate")):
        mm = _by_reader(kept, c).mean()
        out[f"3.5 {nm}, non-simplified (per s)"] = float(mm["non-simplified"])
        out[f"3.5 {nm}, simplified (per s)"] = float(mm["simplified"])
    if "blink" in res.events:                    # Figure 2D: the blink response after the 100 ms padding
        bl = res.events["blink"].summary
        bl = bl[bl["lag"] > 100]
        out["3.5 blink response: largest rise, mean of versions (%)"] = float(bl.groupby("version")["pooled_pct"].max().mean())
        out["3.5 blink response: lowest point, mean of versions (%)"] = float(bl.groupby("version")["pooled_pct"].min().mean())
    if "return_sweep" in res.events:             # Figure 2C: the trace around landing, by eye
        rt = res.events["return_sweep"].summary
        lv = {}
        for e, g in rt.groupby("eye"):
            g = g.set_index("lag")["mean"]
            lv[e] = {"before (-100 to -20 ms)": float(g.loc[-100:-20].mean()), "20 to 120 ms": float(g.loc[20:120].mean()),
                     "120 to 220 ms": float(g.loc[120:220].mean())}
        out["_return_sweep_trace_levels"] = lv
    # 3.6
    out["3.6 trials excluded as skimmed or incomplete"] = int(listed.sum()) + (len(READERS) * N_ITEMS - len(D))
    out["S1 trials kept after the exclusions for skimming and missing data"] = int(len(kept))
    out["3.6 trials read"] = len(READERS) * N_ITEMS
    fig = pr.plot_grand_mean(res.bins, by="version", bin_s=1, max_s=40, min_readers=20)
    gm2 = fig.grand_mean
    plt.close(fig)
    p2 = gm2.pivot(index="sec", columns="level", values="mean")
    dd = (p2["simplified"] - p2["non-simplified"]).dropna()
    out["3.6 grand mean: median difference from 3 s (percentage points)"] = float(dd[dd.index >= 3].median())
    out["_grand_mean"] = gm2
    # 3.7 naive fixation-level test
    from scipy import stats
    F = data.levels.copy()
    F = F[np.isfinite(F["pupil"])]
    F = F.merge(an[["reader", "trial", "version", "baseline_pct"]], on=["reader", "trial"], suffixes=("_f", ""))
    F["rm"] = F["reader"].map(rm)
    F["v"] = 100 * (F["pupil"] - F["baseline_pct"] * F["rm"] / 100) / F["rm"]
    f20 = F[(F["start"] >= 500) & (F["start"] < 20000)]
    tt = stats.ttest_ind(f20.loc[f20["version"] == "simplified", "v"], f20.loc[f20["version"] == "non-simplified", "v"],
                         equal_var=False)
    out["3.7 fixations from 0.5 to 20 s"] = int(len(f20))
    out["3.7 fixation-level t"] = float(tt.statistic)
    pt = _paired(_by_reader(an.dropna(subset=["change_0_20s"]), "change_0_20s"))
    out["3.7 paired t-test on reader means, p"] = pt["p"]
    out["4.4 d_z across readers"] = pt["dz"]
    dz = round(pt["dz"], 3) if ROUND_UP else pt["dz"]
    n_obs, n_03 = _power(dz), _power(0.3)
    out["_readers_for_80pct_power"] = {"observed d_z": pt["dz"], "d_z used": dz, "readers": n_obs,
                                       "readers at the unrounded d_z": _power(pt["dz"]), "readers at d_z = 0.3": n_03}
    up = (lambda n: math.ceil(n - 1e-9)) if ROUND_UP else (lambda n: n)   # whole readers, rounded up
    out["4.4 readers for 80% power"] = up(n_obs)
    out["4.4 readers for 80% power at d_z = 0.3"] = up(n_03)
    # Note S1
    ag = pd.concat([pd.read_csv(os.path.join(cache, r, "detector_agreement.csv"), dtype={"reader": str}) for r in READERS])
    out["S1 detector flags inside padded blinks, median (%)"] = float(ag["pct_padded_caught"].median())
    out["S1 detector flags outside padded blinks, median (%)"] = float(ag["pct_outside"].median())
    out["_S1_outside_mean"] = float(ag["pct_outside"].mean())
    if gamm is not None:
        g = gamm.set_index("model")
        out["3.7 GAMM rho (AR1)"] = float(g.loc["M1 no gaze term", "rho"])
        out["3.7 GAMM M0 residual lag-1"] = float(g.loc["M0 naive", "resid_lag1"])
        out["3.7 GAMM M1 AR1 residual lag-1"] = float(g.loc["M1 no gaze term", "resid_lag1"])
        out["S2 rho without gaze surface"] = float(g.loc["M1 no gaze term", "rho"])
        out["S2 rho with gaze surface"] = float(g.loc["M2 gaze surface", "rho"])
    return out


def control_ladder(res, data):
    """Trial means adjusted for nested sets of control predictors on the same bins (Section 3.7)."""
    b = pr.add_covariates(res.bins, fixations=data.fixations, center=(512, 384), px_per_degree=PX_PER_DEGREE)
    K = {"K1": ["time_s", "time2"]}
    K["K2"] = K["K1"] + ["gaze_x", "gaze_y", "eccentricity"]
    K["K3"] = K["K2"] + ["ink_fovea", "ink_parafovea"]
    K["K4"] = K["K3"] + ["fix_duration", "next_distance"]
    tabs, slopes = None, {}
    for k, cov in K.items():
        adj, sl = pr.control_predictors(b, cov, complete_cases=K["K4"], name=f"controls_{k}")
        slopes[k] = sl
        cols = ["reader", "trial", f"controls_{k}"] + (["change_same_bins"] if tabs is None else [])
        tabs = adj[cols] if tabs is None else tabs.merge(adj[cols], on=["reader", "trial"])
    tabs = tabs.rename(columns={"change_same_bins": "controls_K0"})
    return tabs, slopes


def _fmt(v, d):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return ""
    return f"{v:.{max(d, 0)}f}"


def compare_models(mv, gamm, refs=None):
    t3, s1, ntr = refs or (TABLE3, TABLE_S1, N_TRIALS)
    rows = []
    for table, ref in (("3", t3), ("S1", s1)):
        for name, (e, lo, hi, p) in ref.items():
            if name.startswith("GAMM"):
                if gamm is None:
                    continue
                g = gamm.set_index("model")
                key = name[5:]
                if key not in g.index:
                    continue
                r = g.loc[key]
                new = (r["est"], r["lo"], r["hi"], r["p_avg"], int(r["n_trials"]))
            else:
                r = mv[mv["column"] == name]
                if r.empty:
                    rows.append(dict(table=table, option=name, status="missing"))
                    continue
                r = r.iloc[0]
                new = (r["estimate"], r["lo"], r["hi"], r["p"], int(r["n_trials"]))
            match = all(abs(round(a, 2) - b) < 0.0051 for a, b in zip(new[:3], (e, lo, hi)))
            if p is not None:
                match = match and abs(round(new[3], 3) - p) < 0.00051
            n_exp = ntr.get(name, ntr["default"])
            rows.append(dict(table=table, option=name, paper=f"{e:.2f} [{lo:.2f}, {hi:.2f}]" + (f", p = {p:.3f}" if p is not None else ""),
                             package=f"{new[0]:.2f} [{new[1]:.2f}, {new[2]:.2f}], p = {new[3]:.3f}",
                             estimate=new[0], lo=new[1], hi=new[2], p=new[3], n=new[4], n_paper=n_exp,
                             status="match" if (match and new[4] == n_exp) else "DIFFERS"))
    return pd.DataFrame(rows)


def compare_text(nums, text=None):
    text = text or TEXT
    rows = []
    for name, spec in text.items():
        v, d = spec[0], spec[1]
        new = nums.get(name)
        if new is None:
            rows.append(dict(number=name, paper=v, package="", status="not computed"))
            continue
        if v == "range":
            ok = d <= new <= spec[2]
            rows.append(dict(number=name, paper=f"{d}-{spec[2]}", package=round(float(new), 3), status="match" if ok else "DIFFERS"))
            continue
        if v == "about":
            ok = abs(new - d) <= spec[2]
            rows.append(dict(number=name, paper=f"about {d}", package=round(float(new), 3), status="match" if ok else "DIFFERS"))
            continue
        if d < 0:          # approximate values ("about 200 ms", "about 80 pixels")
            ok = abs(new - v) <= 0.5 * 10 ** (-d)
        elif "r (> .9999)" in name:
            ok = new > 0.9999
        else:
            ok = abs(round(new, d) - v) < 0.6 * 10 ** (-d)
        rows.append(dict(number=name, paper=v, package=round(float(new), max(d, 0) + 2), status="match" if ok else "DIFFERS"))
    return pd.DataFrame(rows)


def compare_old(old, data, T, res, ladder):
    """Trial-by-trial and bin-by-bin comparison with the outputs of the original scripts."""
    R = os.path.join(old, "results")
    P = os.path.join(old, "per_reader")
    rows = []

    def cmp(label, a, b, key=("reader", "item")):
        m = a.merge(b, on=list(key), suffixes=("_new", "_old"))
        x, y = m["v_new"].to_numpy(float), m["v_old"].to_numpy(float)
        both = np.isfinite(x) & np.isfinite(y)
        only = int((np.isfinite(x) != np.isfinite(y)).sum())
        rows.append(dict(quantity=label, compared=int(both.sum()), missing_in_one=only,
                         max_abs_diff=float(np.nanmax(np.abs(x[both] - y[both]))) if both.any() else np.nan))
    Tn = T.copy()
    Tn["reader"] = Tn["reader"].astype(str)
    Tn["item"] = Tn["item"].astype(int)
    old3 = pd.read_csv(os.path.join(R, "03b_trial_measures.csv"))
    old3["reader"] = old3["reader"].map("{:02d}".format)
    an = old3["baseline_pct"] >= 60
    pairs = {"change_0_20s": "change_0_20s", "whole_trial": "change_whole_trial", "interpolated": "change_0_20s_interpolated",
             "baseline_0_500": "change_0_20s_baseline_500", "gaze_regression": "change_0_20s_gaze_regression",
             "gaze_regression_time": "change_0_20s_gaze_regression_time", "no_baseline": "pupil_0_20s_uncorrected",
             "diameter": "change_0_20s_diameter", "baseline_denominator": "change_0_20s_baseline_denominator",
             "fixations": "change_0_20s_fixations", "baseline_pct": "baseline_pct", "duration_s": "duration_s",
             "blink_rate": "blink_rate", "saccade_rate": "saccade_rate", "pct_valid": "pct_valid",
             "low_baselines_kept": "change_0_20s"}
    for new, oldc in pairs.items():
        o = old3[["reader", "item", oldc]].rename(columns={oldc: "v"})
        if new not in ("low_baselines_kept", "baseline_pct", "duration_s", "blink_rate", "saccade_rate", "pct_valid"):
            o = o[an]
        cmp(f"trial: {new} vs 03b {oldc}", Tn[["reader", "item", new]].rename(columns={new: "v"}), o)
    L = pd.read_csv(os.path.join(R, "L_trials.csv"))
    L["reader"] = L["participant"].map("{:02d}".format)
    L = L[L["base_pct"] >= 60]
    for new, oldc in {"window_2_20": "w2_20", "window_3_20": "w3_20", "window_5_20": "w5_20", "cut_1s": "m20_cut1",
                      "cut_2s": "m20_cut2"}.items():
        cmp(f"trial: {new} vs L {oldc}", Tn[["reader", "item", new]].rename(columns={new: "v"}),
            L[["reader", "item", oldc]].rename(columns={oldc: "v"}))
    for f, pairs2 in (("L4_trials.csv", {"gaze_steps_eye": "m20_step_eye", "gaze_steps_reader": "m20_step_reader"}),
                      ("L4E_trials.csv", {"gaze_steps_type": "m20_E1", "gaze_steps_map": "m20_E2"})):
        O = pd.read_csv(os.path.join(R, f))
        O["reader"] = O["participant"].map("{:02d}".format)
        O = O[O["base_pct"] >= 60]
        for new, oldc in pairs2.items():
            cmp(f"trial: {new} vs {f[:-4]} {oldc}", Tn[["reader", "item", new]].rename(columns={new: "v"}),
                O[["reader", "item", oldc]].rename(columns={oldc: "v"}))
    K = pd.read_csv(os.path.join(R, "K_trials.csv"))
    K["reader"] = K["participant"].map("{:02d}".format)
    lad = ladder.merge(data.bins.drop_duplicates(["reader", "trial"])[["reader", "trial", "item"]], on=["reader", "trial"])
    for k in ("K0", "K1", "K2", "K3", "K4"):
        cmp(f"trial: controls_{k} vs K adj_{k}", lad[["reader", "item", f"controls_{k}"]].rename(columns={f"controls_{k}": "v"}),
            K[["reader", "item", f"adj_{k}"]].rename(columns={f"adj_{k}": "v"}))
    # 20 ms bins of the kept trials
    import glob
    ob = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(os.path.join(P, "bins_*.csv.gz")))], ignore_index=True)
    ob["reader"] = ob["participant"].map("{:02d}".format)
    nb = data.bins[["reader", "item", "time", "pupil", "pupil_interp", "n_valid", "gaze_x", "gaze_y"]].copy()
    nb["t"] = nb["time"].round().astype(int)
    mm = nb.merge(ob, left_on=["reader", "item", "t"], right_on=["reader", "item", "t"], how="left")
    for new, oldc in (("pupil", "p_rm"), ("pupil_interp", "p_ip"), ("n_valid", "nvalid"), ("gaze_x", "x"), ("gaze_y", "y")):
        x, y = mm[new].to_numpy(float), mm[oldc].to_numpy(float)
        both = np.isfinite(x) & np.isfinite(y)
        rows.append(dict(quantity=f"20 ms bins: {new} vs per_reader {oldc}", compared=int(both.sum()),
                         missing_in_one=int((np.isfinite(x) != np.isfinite(y)).sum()),
                         max_abs_diff=float(np.abs(x[both] - y[both]).max()) if both.any() else np.nan))
    rows.append(dict(quantity="20 ms bins of kept trials: new bins without an old bin", compared=int(len(mm)),
                     missing_in_one=int(mm["nvalid"].isna().sum()), max_abs_diff=np.nan))
    # trial-level data loss
    ot = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(os.path.join(P, "trials_*.csv")))], ignore_index=True)
    ot["reader"] = ot["participant"].map("{:02d}".format)
    nt = data.trials.copy()
    nt["item"] = nt["item"].astype(int)
    for new, oldc in (("pct_valid", "pct_valid"), ("pct_invalid", "pct_invalid"), ("pct_blink_pad", "pct_blinkpad_loss"),
                      ("duration_s", "dur_s"), ("n_blinks", "blink_n"), ("n_saccades", "sacc_n")):
        cmp(f"trial data loss: {new} vs per_reader {oldc}", nt[["reader", "item", new]].rename(columns={new: "v"}),
            ot[["reader", "item", oldc]].rename(columns={oldc: "v"}))
    # saccade steps
    os_ = pd.read_csv(os.path.join(R, "L4_saccades.csv.gz"))
    os_["reader"] = os_["participant"].map("{:02d}".format)
    ns = res.steps.copy()
    ns["item"] = ns["item"].astype(int)
    rows.append(dict(quantity="saccades with a step: new vs old", compared=int(np.isfinite(ns["step"]).sum()),
                     missing_in_one=int(np.isfinite(os_["step"]).sum()), max_abs_diff=np.nan))
    a = ns.sort_values(["reader", "item", "landing"]).reset_index(drop=True)
    b = os_.sort_values(["reader", "item", "L"]).reset_index(drop=True)
    if len(a) == len(b):
        for new, oldc in (("step", "step"), ("late", "late"), ("dx", "dx"), ("dy", "dy"), ("landing", "L")):
            x, y = a[new].to_numpy(float), b[oldc].to_numpy(float)
            both = np.isfinite(x) & np.isfinite(y)
            rows.append(dict(quantity=f"saccades: {new} vs L4 {oldc}", compared=int(both.sum()),
                             missing_in_one=int((np.isfinite(x) != np.isfinite(y)).sum()),
                             max_abs_diff=float(np.abs(x[both] - y[both]).max())))
    # GAMM bins
    og = pd.read_csv(os.path.join(R, "H_gamm_bins100.csv.gz"))
    og["reader"] = og["participant"].map("{:02d}".format)
    ng = pd.read_csv(os.path.join(res.files["bins.csv"]), dtype={"reader": str})
    ng = ng[ng["baseline_pct"] >= 60]
    ng["t100"] = (ng["time"] * 1000 - 50).round().astype(int)
    m3 = ng.merge(og, on=["reader", "item", "t100"], how="outer", indicator=True)
    rows.append(dict(quantity="100 ms bins: rows only in one", compared=int((m3["_merge"] == "both").sum()),
                     missing_in_one=int((m3["_merge"] != "both").sum()), max_abs_diff=np.nan))
    m3 = m3[m3["_merge"] == "both"]
    for new, oldc in (("pupil_change", "rel"), ("gaze_x", "x"), ("gaze_y", "y")):
        x, y = m3[new].to_numpy(float), m3[oldc].to_numpy(float)
        both = np.isfinite(x) & np.isfinite(y)
        rows.append(dict(quantity=f"100 ms bins: {new} vs H {oldc}", compared=int(both.sum()),
                         missing_in_one=int((np.isfinite(x) != np.isfinite(y)).sum()),
                         max_abs_diff=float(np.abs(x[both] - y[both]).max())))
    return pd.DataFrame(rows)


def run_r(script, args, cwd, env=None, log=None):
    e = dict(os.environ)
    e.update(env or {})
    t0 = time.time()
    with open(log, "w") if log else open(os.devnull, "w") as fh:
        r = subprocess.run(["Rscript", script] + list(args), cwd=cwd, env=e, stdout=fh, stderr=subprocess.STDOUT)
    print(f"  {os.path.basename(script)} finished in {(time.time() - t0) / 60:.1f} min (exit {r.returncode})", flush=True)
    return r.returncode


def is_legacy(cache):
    """True when the cache was prepared with ``prepare --legacy``."""
    for r in READERS:
        f = os.path.join(cache, r, "done.json")
        if os.path.exists(f):
            with open(f) as fh:
                return bool(json.load(fh).get("legacy", False))
    return False


def cmd_analyse(a):
    t0 = time.time()
    os.makedirs(a.out, exist_ok=True)
    cfg = pr.load_config(study_config(a.cache))
    legacy = is_legacy(a.cache)
    global ROUND_UP
    ROUND_UP = not legacy
    refs = (ORIGINAL_TABLE3, ORIGINAL_TABLE_S1, ORIGINAL_N_TRIALS) if legacy else (TABLE3, TABLE_S1, N_TRIALS)
    text_ref = ORIGINAL_TEXT if legacy else TEXT
    print("compared with the values of the " + ("original scripts (legacy cache)" if legacy else "paper"), flush=True)
    state = os.path.join(a.out, "state.pkl")
    if a.reuse and os.path.exists(state):
        import pickle
        with open(state, "rb") as fh:
            data, res, T, ladder = pickle.load(fh)
        print(f"pooled results read from {state}", flush=True)
    else:
        data = pr.prepare_readers(None, cfg, cache=a.cache, verbose=False)
        print(f"{len(data.readers)} readers read from the cache ({time.time() - t0:.0f} s)", flush=True)
        same = add_ink(data.bins, os.path.join(a.cache, "ia"))
        print("layouts identical across readers of a set:", same, flush=True)
        res = pr.analyse(data, cfg)
        T = res.options.copy()
        ladder, ksl = control_ladder(res, data)
        T = T.merge(ladder, on=["reader", "trial"], how="left")
        spec = pd.DataFrame(res.options.attrs["options"])
        labels = {"K0": "Control predictors: none, same bins", "K1": "Control predictors: time",
                  "K2": "Control predictors: + gaze x, y, eccentricity", "K3": "Control predictors: + local text density",
                  "K4": "Control predictors: + fixation duration, distance to next fixation"}
        spec = pd.concat([spec, pd.DataFrame([dict(column=f"controls_{k}", label=v, random="slope", covariates="",
                                                   term="contrast", section="3.7", table="text")
                                              for k, v in labels.items()])], ignore_index=True)
        T.attrs = {"options": spec.to_dict("records")}
        files = pr.export_for_r(T, res.bins, os.path.join(a.out, "for_R"), reference="non-simplified", config=cfg)
        res.files.update(files)
        print(f"files for R written ({time.time() - t0:.0f} s)", flush=True)
        import pickle
        with open(state, "wb") as fh:
            pickle.dump((data, res, T, ladder), fh, protocol=4)
    fr = os.path.join(a.out, "for_R")
    run_r("multiverse.R", ["trials.csv", "options.csv", "multiverse_results.csv"], fr, log=os.path.join(fr, "multiverse_log.txt"))
    run_r("lmm.R", ["trials.csv", "lmm_results.csv"], fr, log=os.path.join(fr, "lmm_log.txt"))
    gamm = None
    gs = os.path.join(fr, "gamm", "gamm_summary.csv")
    if a.gamm and not os.path.exists(gs):
        run_r("gamm.R", ["bins.csv", "gamm"], fr, env={"NTHREADS": "2"}, log=os.path.join(fr, "gamm_stdout.txt"))
    if os.path.exists(gs):
        gamm = pd.read_csv(gs)
    if a.kcheck and not os.path.exists(os.path.join(fr, "kcheck", "gamm_kcheck.csv")):
        run_r(os.path.join(HERE, "gamm_kcheck.R"), ["bins.csv", "kcheck"], fr, env={"NTHREADS": "2"},
              log=os.path.join(fr, "kcheck_stdout.txt"))
    mv = pd.read_csv(os.path.join(fr, "multiverse_results.csv"))
    cm = compare_models(mv, gamm, refs)
    cm.to_csv(os.path.join(a.out, "compare_tables.csv"), index=False)
    nums = text_numbers(res, data, T, a.cache, gamm)
    if gamm is not None:
        log = open(os.path.join(fr, "gamm", "gamm_log.txt")).read()
        import re
        k = re.findall(r"excess kurtosis ([0-9.]+)", log)
        if len(k) >= 2:
            nums["S2 excess kurtosis without gaze surface"] = float(k[0])
            nums["S2 excess kurtosis with gaze surface"] = float(k[1])
    kc = os.path.join(fr, "kcheck", "gamm_kcheck.csv")
    if os.path.exists(kc):
        K = pd.read_csv(kc)
        for i, k in ((0, 3), (1, 5)):
            nums[f"S2 k-check, k = {k}: estimate (%)"] = float(K.loc[i, "est"])
            nums[f"S2 k-check, k = {k}: lower (%)"] = float(K.loc[i, "lo"])
            nums[f"S2 k-check, k = {k}: upper (%)"] = float(K.loc[i, "hi"])
        if "n_readers" in K.columns:
            nums["S2 k-check readers"] = int(K.loc[0, "n_readers"])
            nums["S2 k-check trials"] = int(K.loc[0, "n_trials"])
    t3 = cm[(cm["table"] == "3") & cm["estimate"].notna()] if "estimate" in cm.columns else cm.iloc[0:0]
    if len(t3):
        nums["5 smallest estimate in Table 3 (%)"] = float(t3["estimate"].min())
        nums["5 largest estimate in Table 3 (%)"] = float(t3["estimate"].max())
    k0 = mv.set_index("column")["estimate"]
    nums["3.7 control predictors, no adjustment on the same bins (%)"] = float(k0.get("controls_K0", np.nan))
    nums["3.7 control predictors, all (%)"] = float(k0.get("controls_K4", np.nan))
    nums["3.7 text density changed the estimate by (percentage points)"] = float(k0.get("controls_K3", np.nan) - k0.get("controls_K2", np.nan))
    ct = compare_text(nums, text_ref)
    ct.to_csv(os.path.join(a.out, "compare_text.csv"), index=False)
    extra = {k: v for k, v in nums.items() if k.startswith("_") and not isinstance(v, pd.DataFrame)}
    with open(os.path.join(a.out, "extra_numbers.json"), "w") as fh:
        json.dump(extra, fh, indent=1, default=float)
    for k, v in nums.items():
        if isinstance(v, pd.DataFrame):
            v.to_csv(os.path.join(a.out, f"{k.strip('_')}.csv"), index=False)
    for k, e in res.events.items():                     # event-locked traces for Figure 2C-D
        e.summary.to_csv(os.path.join(a.out, f"events_{k}.csv"), index=False)
    allb = [os.path.join(a.cache, r, "blink_events_all_trials.csv.gz") for r in READERS]
    if all(os.path.exists(f) for f in allb):
        BR = pd.concat([pd.read_csv(f, dtype={"reader": str}) for f in allb], ignore_index=True)
        if "reader_mean" not in BR.columns:
            BR["reader_mean"] = BR["reader"].map(pr.reader_means(data.bins))
        pr.summarise_events(BR, "version").summary.to_csv(os.path.join(a.out, "events_blink_all_trials.csv"), index=False)
    if a.old:
        co = compare_old(a.old, data, T, res, ladder)
        co.to_csv(os.path.join(a.out, "compare_old_outputs.csv"), index=False)
        print(co.to_string(index=False))
    pd.set_option("display.width", 200)
    print(cm.to_string(index=False))
    print(ct.to_string(index=False))
    print(f"done in {(time.time() - t0) / 60:.1f} min; results in {a.out}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("prepare")
    s1.add_argument("--data", required=True, help="the 'Full study results' folder (SET 1, SET 2, RUN_IN_R)")
    s1.add_argument("--cache", required=True)
    s1.add_argument("--readers", help="comma-separated subset")
    s1.add_argument("--max-seconds", type=float, default=0, help="stop after this many seconds (resume later)")
    s1.add_argument("--force", action="store_true", help="prepare readers again even if they are in the cache")
    s1.add_argument("--legacy", action="store_true", help="impose the original scripts' assumptions (see legacy_mode)")
    s2 = sub.add_parser("analyse")
    s2.add_argument("--cache", required=True)
    s2.add_argument("--out", required=True)
    s2.add_argument("--old", help="folder with the original per_reader/ and results/ for trial-by-trial checks")
    s2.add_argument("--gamm", action="store_true", help="fit the GAMMs (about 30 minutes, 6 GB)")
    s2.add_argument("--kcheck", action="store_true", help="basis-dimension check of Note S2 (about 15 minutes)")
    s2.add_argument("--reuse", action="store_true", help="reuse the pooled results of an earlier run (out/state.pkl)")
    a = p.parse_args(argv)
    {"prepare": cmd_prepare, "analyse": cmd_analyse}[a.cmd](a)


if __name__ == "__main__":
    main()
