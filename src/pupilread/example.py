"""Synthetic example data in the format of EyeLink Data Viewer reports, for the quick start and the tests.

The simulated readers read passages line by line (forward saccades, regressions, return sweeps), blink about every
3 s, and show a light reflex after text onset, a slow decline of pupil size and a small difference between versions.
Measured pupil size also depends on gaze position (the foreshortening artifact of Section 3.4), more for the left eye.
None of the values are real data.
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np
import pandas as pd
from scipy.signal import lfilter

SAMPLE_COLS = ["RECORDING_SESSION_LABEL", "TRIAL_INDEX", "TIMESTAMP", "TRIAL_START_TIME", "EYE_TRACKED",
               "LEFT_PUPIL_SIZE", "LEFT_GAZE_X", "LEFT_GAZE_Y", "LEFT_IN_BLINK", "LEFT_IN_SACCADE",
               "RIGHT_PUPIL_SIZE", "RIGHT_GAZE_X", "RIGHT_GAZE_Y", "RIGHT_IN_BLINK", "RIGHT_IN_SACCADE", "SAMPLE_MESSAGE"]
#: Simulated artifact per pixel of gaze offset from the screen centre, as a share of pupil size (x, y), by eye.
ARTIFACT = {"left": (-0.00014, -0.0004), "right": (-0.00006, -0.0001)}
#: An invented layout (mm) for the example's layout.csv (see pupilread.read_layout): a 400 x 300 mm image at 600 mm,
#: centred on the head, eyes 200 mm below its top edge, camera lens 180 mm below and 480 mm in front of the eyes.
EXAMPLE_LAYOUT = [
    ("image_width", 400, "visible image, mm"), ("image_height", 300, "visible image, mm"),
    ("width_px", 1024, "pixels"), ("height_px", 768, "pixels"),
    ("Sx", -200, "upper-left corner of the image, right of the midline (mm)"),
    ("Sy", 200, "upper-left corner of the image, above the eyes (mm)"), ("Sz", 600, "eyes to screen (mm)"),
    ("Cx", 0, "camera lens, right of the midline (mm)"), ("Cy", -180, "camera lens, above the eyes (mm)"),
    ("Cz", 480, "camera lens, in front of the eyes (mm)"), ("eye", "midline", "positions measured from the midline"),
    ("eye_separation", 64, "between the eyes (mm)"),
]


def _layout(rng, n_lines, words_per_line, x0=100, y0=120, line_h=48, right=920):
    words = []
    for k in range(n_lines):
        x = x0
        for _ in range(words_per_line):
            w = rng.uniform(40, 90)
            if x + w > right:
                break
            words.append((x, x + w, y0 + k * line_h, k))
            x += w + 10
    return np.array(words)


def _scanpath(rng, words):
    """Fixations (word index, x, y, duration) reading the words in order, with skips and regressions."""
    fix = []
    i = 0
    n = len(words)
    while i < n:
        l, r, y, line = words[i]
        x = l + (r - l) * rng.uniform(0.3, 0.6) + rng.normal(0, 3)
        d = 80 + rng.gamma(4.0, 40.0) if rng.random() > 0.08 else rng.uniform(50, 79)
        fix.append((i, x, y + rng.normal(0, 3), d))
        if rng.random() < 0.04 and line > 0:          # look up to the line above and back (vertical saccades)
            up = np.flatnonzero((words[:, 3] == line - 1) & (np.abs((words[:, 0] + words[:, 1]) / 2 - x) < 60))
            if up.size:
                l2, r2, y2, _ = words[up[0]]
                fix.append((int(up[0]), (l2 + r2) / 2, y2 + rng.normal(0, 3), 80 + rng.gamma(4.0, 35.0)))
                fix.append((i, x + rng.normal(0, 4), y + rng.normal(0, 3), 80 + rng.gamma(4.0, 30.0)))
        if rng.random() < 0.10 and i > 0 and words[i - 1][3] == line:
            j = i - int(rng.integers(1, 3))
            j = max(j, 0)
            if words[j][3] == line:
                l2, r2, y2, _ = words[j]
                fix.append((j, l2 + (r2 - l2) * 0.5, y2 + rng.normal(0, 3), 80 + rng.gamma(4.0, 35.0)))
        i += 2 if rng.random() < 0.18 else 1
    return fix


def _trial(rng, reader_mean, eye, version, n_lines, words_per_line, hz, onset_ms, low_baseline=False, heavy_loss=False):
    words = _layout(rng, n_lines + (1 if version == "simplified" else 0), words_per_line)
    fixes = _scanpath(rng, words)
    # time line (ms from trial start): pre-onset fixation, then fixations separated by saccades or blinks
    events = []          # (kind, start, end, x0, y0, x1, y1, word)
    t = onset_ms + 120.0
    events.append(("fix", 0.0, t, words[0][0] + 15, words[0][2], words[0][0] + 15, words[0][2], -1))
    prev = (words[0][0] + 15, words[0][2])
    next_blink = t + rng.exponential(3000)
    for (w, x, y, d) in fixes:
        amp = np.hypot(x - prev[0], y - prev[1])
        if t > next_blink:
            dur = rng.uniform(80, 250)
            events.append(("blink", t, t + dur + 30, prev[0], prev[1], x, y, -1))
            t += dur + 30
            next_blink = t + rng.exponential(3000)
        else:
            sd = 18 + 0.08 * amp
            events.append(("sacc", t, t + sd, prev[0], prev[1], x, y, -1))
            t += sd
        events.append(("fix", t, t + d, x, y, x, y, w))
        t += d
        prev = (x, y)
    end_ms = t + 250
    n = int(np.ceil((end_ms + 150) * hz / 1000.0))
    tt = np.arange(n) * 1000.0 / hz
    gx = np.full(n, np.nan)
    gy = np.full(n, np.nan)
    blink = np.zeros(n, bool)
    sacc = np.zeros(n, bool)
    for kind, a, b, x0, y0, x1, y1, w in events:
        m = (tt >= a) & (tt < b)
        if kind == "fix":
            gx[m] = x0 + rng.normal(0, 0.4, m.sum())
            gy[m] = y0 + rng.normal(0, 0.4, m.sum())
        elif kind == "sacc":
            f = (tt[m] - a) / max(b - a, 1)
            gx[m] = x0 + (x1 - x0) * f
            gy[m] = y0 + (y1 - y0) * f
            sacc[m] = True
        else:
            core = (tt >= a + 15) & (tt < b - 15)
            blink[core] = True
            sacc[m] = True
    last = (tt >= t)
    gx[last] = prev[0]
    gy[last] = prev[1]
    # pupil: light reflex 220 ms after onset, slow decline, effort, noise
    rel = np.where(tt < onset_ms + 220, 0.10, 0.10 - 0.15 * (1 - np.exp(-(tt - onset_ms - 220) / 350.0)))
    s_on = np.clip((tt - onset_ms) / 1000.0, 0, None)
    rel = rel - 0.003 * s_on + (0.015 if version == "simplified" else 0.0) * (1 - np.exp(-s_on / 2.0))
    ar = lfilter([1.0], [1.0, -0.998], rng.normal(0, 0.0012, n))
    rel = rel + ar + rng.normal(0, 0.03)
    ax, ay = ARTIFACT[eye]
    art = 1 + ax * (np.nan_to_num(gx, nan=512) - 512) + ay * (np.nan_to_num(gy, nan=384) - 384)
    pupil = reader_mean * (1 + rel) * art
    # blink edges: the lid partly covers the pupil for 15 ms on each side of a blink
    edge = np.zeros(n, bool)
    for kind, a, b, *_ in events:
        if kind == "blink":
            edge |= ((tt >= a) & (tt < a + 15)) | ((tt >= b - 15) & (tt < b))
    pupil[edge] *= rng.uniform(0.3, 0.8, edge.sum())
    pupil[blink] = np.nan
    gx[blink] = np.nan
    gy[blink] = np.nan
    if low_baseline:      # a squint in the baseline window, not marked as a blink
        m = (tt >= onset_ms) & (tt < onset_ms + 260)
        pupil[m] *= 0.45
    if heavy_loss:        # tracking lost for most of the trial
        m = (tt >= onset_ms + 3000) & (tt < end_ms - 1500)
        pupil[m] = np.nan
        gx[m] = np.nan
        gy[m] = np.nan
    pupil = np.round(pupil)
    fx = []
    for kind, a, b, x0, y0, *_rest in events:
        if kind != "fix" or b - a <= 0:
            continue
        m = (tt >= a) & (tt < b)
        fx.append((a, b, x0, y0, float(np.nanmean(pupil[m])) if np.isfinite(pupil[m]).any() else np.nan, _rest[-1]))
    return tt, pupil, gx, gy, blink, sacc, end_ms, fx, events


def make_example(folder: str = "pupilread_example", n_readers: int = 3, n_items: int = 4, n_lines: int = 10,
                 words_per_line: int = 12, hz: float = 1000.0, seed: int = 2026, onset_ms: float = 1000.0) -> dict:
    """Write synthetic Data Viewer sample, message and fixation reports for a small study, with design.csv.

    Each reader reads ``n_items`` passages, half in each version ("simplified" or "non-simplified", counterbalanced
    across readers). One trial per study loses most of its samples (to exercise trial exclusion) and one has a
    distorted baseline (to exercise the low-baseline check).

    Returns
    -------
    dict
        Paths: ``folder``, ``design`` (design.csv), ``exclusions`` (exclusions.csv, one trial flagged as skimmed),
        ``layout`` (layout.csv, an invented layout of eye, camera and screen for the geometric correction; the
        simulated artifact does not follow it) and ``readers`` (one dict per reader with its three reports).
    """
    rng = np.random.default_rng(seed)
    os.makedirs(folder, exist_ok=True)
    design, readers = [], []
    for ri in range(n_readers):
        reader = f"{ri + 1:02d}"
        eye = "right" if ri % 2 == 0 else "left"
        rm = rng.uniform(1100, 1800)
        d = os.path.join(folder, reader)
        os.makedirs(d, exist_ok=True)
        samples, msgs, fixs = [], [], []
        clock = 1_000_000.0 + ri * 10_000_000
        for item in range(1, n_items + 1):
            version = "simplified" if (item + ri) % 2 == 0 else "non-simplified"
            design.append((reader, item, item, version))
            tt, pupil, gx, gy, blink, sacc, end_ms, fx, events = _trial(
                rng, rm, eye, version, n_lines, words_per_line, hz, onset_ms,
                low_baseline=(ri == 0 and item == 2), heavy_loss=(ri == n_readers - 1 and item == n_items))
            start = clock
            ts = np.round(start + tt).astype(np.int64)
            n = len(tt)
            E = eye.upper()
            cols = {c: np.full(n, np.nan) for c in SAMPLE_COLS}
            cols["RECORDING_SESSION_LABEL"] = np.full(n, reader, dtype=object)
            cols["TRIAL_INDEX"] = np.full(n, item)
            cols["TIMESTAMP"] = ts
            cols["TRIAL_START_TIME"] = np.full(n, int(round(start)))
            cols["EYE_TRACKED"] = np.full(n, E, dtype=object)
            cols[f"{E}_PUPIL_SIZE"] = pupil
            cols[f"{E}_GAZE_X"] = np.round(gx, 1)
            cols[f"{E}_GAZE_Y"] = np.round(gy, 1)
            cols[f"{E}_IN_BLINK"] = blink.astype(int)
            cols[f"{E}_IN_SACCADE"] = sacc.astype(int)
            sm = np.full(n, None, dtype=object)
            msg = [(item, 0.0, "TRIALID"), (item, onset_ms, "DISPLAY_target"), (item, round(end_ms), "KEYBOARD_endTarget")]
            for _, mt, text in msg:
                k = int(round(mt * hz / 1000.0))
                if 0 <= k < n:
                    sm[k] = text
            cols["SAMPLE_MESSAGE"] = sm
            S = pd.DataFrame(cols)[SAMPLE_COLS]
            samples.append(S)
            msgs += [(reader, it, mt, text) for it, mt, text in msg]
            blink_ends = [b for kind, a, b, *_ in events if kind == "blink"]
            blink_starts = [a for kind, a, b, *_ in events if kind == "blink"]
            for (a, b, x, y, p, w) in fx:
                before = any(abs(a - be) < 1 for be in blink_ends)
                after = any(abs(b - bs) < 1 for bs in blink_starts)
                around = "BOTH" if before and after else "BEFORE" if before else "AFTER" if after else "NONE"
                fixs.append((reader, item, round(a), round(b), round(b) - round(a), x, y, p, around,
                             w + 1 if w >= 0 else np.nan))
            clock += end_ms + 200 + 5000
        S = pd.concat(samples, ignore_index=True)
        p_s = os.path.join(d, "sample_report.txt")
        S.to_csv(p_s, sep="\t", index=False, na_rep=".")
        M = pd.DataFrame(msgs, columns=["RECORDING_SESSION_LABEL", "TRIAL_INDEX", "CURRENT_MSG_TIME", "CURRENT_MSG_TEXT"])
        p_m = os.path.join(d, "message_report.txt")
        M.to_csv(p_m, sep="\t", index=False, na_rep=".")
        F = pd.DataFrame(fixs, columns=["RECORDING_SESSION_LABEL", "TRIAL_INDEX", "CURRENT_FIX_START", "CURRENT_FIX_END",
                                        "CURRENT_FIX_DURATION", "CURRENT_FIX_X", "CURRENT_FIX_Y", "CURRENT_FIX_PUPIL",
                                        "CURRENT_FIX_BLINK_AROUND", "CURRENT_FIX_INTEREST_AREA_ID"])
        F["CURRENT_FIX_X"] = F["CURRENT_FIX_X"].round(1)
        F["CURRENT_FIX_Y"] = F["CURRENT_FIX_Y"].round(1)
        F["CURRENT_FIX_PUPIL"] = F["CURRENT_FIX_PUPIL"].round(1)
        p_f = os.path.join(d, "fixation_report.txt")
        F.to_csv(p_f, sep="\t", index=False, na_rep=".")
        readers.append({"reader": reader, "samples": p_s, "messages": p_m, "fixations": p_f})
    D = pd.DataFrame(design, columns=["reader", "trial", "item", "version"])
    p_d = os.path.join(folder, "design.csv")
    D.to_csv(p_d, index=False)
    X = pd.DataFrame({"reader": [readers[min(1, n_readers - 1)]["reader"]], "trial": [1], "reason": ["skimmed"]})
    p_x = os.path.join(folder, "exclusions.csv")
    X.to_csv(p_x, index=False)
    p_l = os.path.join(folder, "layout.csv")
    pd.DataFrame(EXAMPLE_LAYOUT, columns=["setting", "value", "note"]).to_csv(p_l, index=False)
    return {"folder": folder, "design": p_d, "exclusions": p_x, "layout": p_l, "readers": readers}
