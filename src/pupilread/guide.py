"""Plain-language guide to the functions of Table 1 of the paper: ``pupilread.guide()``."""
from __future__ import annotations

import re
import textwrap
from typing import Optional

INTRO = ("The functions of Table 1 of the paper, by stage. Every setting defaults to the paper's choice, so calling a "
         "function without changing anything repeats the paper's analysis. Full description of a function and all "
         "its settings: help(pr.baseline), for example.")

#: (stage, title, [(function, paragraphs)]) in the order of Table 1.
STAGES = [
    ("3.1", "Data level", [
        ("read_eyelink()", [
            "Reads a Data Viewer sample report into a table with one row per sample.",
            "The message report gives the time of text onset and of the key press that ended reading, so only the "
            "reading time is kept, with time 0 at text onset. The design file adds each trial's item and version.",
            "It keeps the recorded eye, reads only the columns it needs and drops duplicated rows.",
        ]),
        ("read_fixations()", [
            "Reads the fixation report into a table with one row per fixation: start, end, duration, position, pupil "
            "size and whether a blink is next to it, on the same time axis as the samples. The fixation-based steps "
            "need it.",
        ]),
        ("bin()", [
            "Averages the samples in 20 ms bins; a bin counts only if at least half of its samples are valid. This "
            "lowers the rate to 50 Hz and smooths the signal.",
        ]),
        ("compare_levels()", [
            "Checks the choice between samples and fixations. For each fixation of at least 80 ms with no blink next "
            "to it, it compares the fixation's pupil value with the mean of the samples inside it.",
            "It reports the agreement (r), the mean difference and the share of reading time that fixations cover. "
            "In the paper: r > .9999, 73% of reading time.",
        ]),
        ("plot_trial()", [
            "Draws Figure 2: one trial as raw samples, after blink removal, in 20 ms bins and after baseline "
            "correction. It runs these steps itself, so it takes the samples, not the bins.",
            "Over a whole trial, the bins look like the samples. zoom=(3.0, 3.5) adds a close-up of half a second "
            "below the four steps, so each bin mean can be seen against its samples.",
        ]),
    ]),
    ("3.2", "Blinks and artifacts", [
        ("detect_blinks()", [
            "For eye trackers that do not mark blinks. It flags samples where pupil size is missing, implausible or "
            "changing faster than the trial's median speed plus 16 median absolute deviations (the dilation-speed "
            "filter of Kret & Sjak-Shie, 2019).",
            "The paper did not need it, because EyeLink marks blinks; Supplementary Note S1 compares the two.",
        ]),
        ("pad_blinks()", [
            "Widens every blink by 100 ms on each side and sets those samples to missing, because pupil size is "
            "distorted just before and after a blink. Values outside 100 to 10,000 area units also count as invalid.",
        ]),
        ("interpolate()", [
            "An option. It fills gaps of up to 1 s from the valid samples on either side, in a separate column, so "
            "removal stays the default. In the paper, it left the primary estimate unchanged (Table S2).",
        ]),
        ("exclude_trials()", [
            "Drops trials with fewer than half of their samples valid, and trials listed in an exclusion file. It "
            "returns the kept samples and a table giving the reason for each exclusion.",
            "In the paper: 12 trials for missing data, and 61 listed as skimmed or incomplete.",
        ]),
    ]),
    ("3.3", "Baseline", [
        ("baseline()", [
            "Subtracts each trial's baseline, its mean pupil size from 0 to 200 ms after text onset, and expresses "
            "the change as a percentage of the reader's mean pupil size, which makes readers and eyes comparable.",
            "Alternatives: another window, such as window=(0, 500), divisive correction (method=\"divisive\") or no "
            "correction (method=\"none\").",
        ]),
        ("low_baselines()", [
            "Flags trials whose baseline is missing or below 60% of the reader's mean. Such baselines come from "
            "blinks at text onset and inflate the corrected values. R 1 drops these trials.",
            "In the paper: 19 missing and 2 low baselines. plot_baselines() shows where to set the cut-off.",
        ]),
    ]),
    ("3.4", "Gaze position", [
        ("saccade_steps()", [
            "For every saccade between two fixations, measures the step in pupil size from just before it to 20 to "
            "120 ms after landing. Real pupil responses start no earlier than about 220 ms after their cause, so a "
            "step this fast is an artifact of gaze position. It also records each saccade's size and type: forward, "
            "regression, return sweep or vertical.",
        ]),
        ("step_slopes()", [
            "Turns the steps into the artifact per pixel of gaze shift for each recorded eye, from a regression of "
            "the steps on horizontal and vertical saccade size.",
        ]),
        ("regression_slopes()", [
            "The alternative in Table 2: it estimates the artifact by regressing pupil size on gaze position in the "
            "reading data itself. Because gaze moves with progress through the text, these slopes can absorb part "
            "of a real effect or enlarge it; the saccade steps avoid that.",
        ]),
        ("correct_gaze()", [
            "Removes the artifact from every bin according to where the eye was looking. It must run before "
            "baseline(), and it warns if the order is wrong.",
            "The primary estimate uses no correction (method=None). The options are \"steps\" (with step_slopes()), "
            "\"regression\" (with regression_slopes()), \"geometric\" (needs the measured layout of eye, camera and "
            "screen) and \"hybrid\" (exploratory).",
        ]),
    ]),
    ("3.5", "Trial length", [
        ("trial_means()", [
            "Gives one value per trial: the mean change from 0.5 to 20 s. The window is the same in both versions, "
            "so the shorter simplified trials are not compared over a different part of the slow decline in pupil "
            "size.",
            "window=(500, None) gives the whole-trial mean instead, and cut_before_keypress_ms leaves out the run-up "
            "to the key press.",
        ]),
        ("event_response()", [
            "Shows the pupil around one type of event: blinks (Figure 3D), saccades or return sweeps (Figure 3C). It "
            "returns each reader's mean response and their mean across readers.",
        ]),
    ]),
    ("3.6", "Quality checks", [
        ("data_loss()", [
            "Per trial: the percentage of invalid samples, of samples lost to the padding and of valid samples, trial "
            "length, and blink and saccade rates; and their summary by version. In the paper: 10.1% of samples lost; "
            "trials of 43.2 s (non-simplified) and 38.5 s (simplified).",
        ]),
        ("plot_overlays()", [
            "Draws every trial's trace, one panel per reader, to catch spikes and gaps that averages hide. In the "
            "paper, 26% of trials showed residual spikes.",
        ]),
        ("plot_baselines()", [
            "A histogram of the baselines, with a panel of log-scaled counts so that rare low baselines show. Use it "
            "to set the cut-off of low_baselines() (60% in the paper).",
        ]),
        ("plot_grand_mean()", [
            "Draws Figure 3B: the mean time course of each version in 1 s steps, with 95% confidence intervals, "
            "drawing only time points with at least 20 readers.",
        ]),
        ("plot_quality()", [
            "Plots data loss and blink and saccade rates by version, with each reader's two values joined, to show "
            "whether data quality differs between versions.",
        ]),
        ("plot_gaze()", [
            "Plots mean gaze position by version relative to the baseline, which shows where the versions differ in "
            "gaze. In the paper, gaze in simplified texts lay about 80 pixels further left and 40 pixels lower.",
        ]),
    ]),
    ("3.7", "Modelling", [
        ("control_predictors()", [
            "Adjusts each trial mean for time, gaze position and distance from the screen centre, fixation duration "
            "and the distance to the next fixation, and for any study-specific predictor, such as local text "
            "density. The slopes are estimated within trials, so the version difference, which lies between trials, "
            "stays out of them.",
            "With text density, as in the paper, this gives the control-predictors row of Table 3.",
        ]),
        ("export_for_r()", [
            "Writes the files for R: trials.csv (one row per trial; contrast = 0 for the reference version, "
            "non-simplified in the paper, and 1 for the other), bins.csv (100 ms bins from 0.5 to 20 s, for the "
            "time-course model) and copies of the R scripts.",
        ]),
        ("lmm.R", [
            "R 1: the mixed model of the trial means, on trials with baselines of at least 60%:",
            "change_0_20s ~ contrast + (1 | reader) + (0 + contrast | reader) + (1 | item)",
            "In words: the version difference, with a level and a version difference for each reader and a level for "
            "each text.",
            "In the paper, this gives the primary estimate, 1.37 [-0.20, 2.94], p = .087.",
        ]),
        ("gamm.R", [
            "R 2: the time-course models (mgcv). They estimate the version difference over the first 20 s with a "
            "smooth for each trial, the random effects of R 1, and an AR1 term for the similarity of neighbouring "
            "100 ms bins; a second model adds a gaze-position surface.",
            "In the paper: the GAMM rows of Table 3 (1.33, and 1.96 with the gaze surface), in about 30 minutes.",
        ]),
    ]),
]


def _entries():
    for stage, title, funcs in STAGES:
        for name, paras in funcs:
            yield stage, title, name, paras


def topics():
    """The stages and functions that :func:`guide` explains."""
    return [s for s, _, _ in STAGES] + [name for _, _, name, _ in _entries()]


def _key(name: str) -> str:
    return name.lower().strip().removeprefix("pr.").removeprefix("pupilread.").replace("()", "")


_NBSP = "\u00a0"
_UNIT = re.compile(r"(\d) (ms|s|Hz|pixels|readers)\b")
_LABEL = re.compile(r"\b(Table|Figure|Note|Section|R) (S?\d)")


def _fill(text: str, width: int, indent: str = "") -> str:
    """Wrap ``text`` without separating a number from its unit or a table or figure name from its number."""
    kept = _LABEL.sub(rf"\1{_NBSP}\2", _UNIT.sub(rf"\1{_NBSP}\2", text))
    out = textwrap.fill(kept, width, initial_indent=indent, subsequent_indent=indent)
    return out.replace(_NBSP, " ")


def _format(name: str, paras, width: int) -> str:
    body = "\n".join(_fill(p, width, "    ") for p in paras)
    return f"  {name}\n{body}\n"


def guide(topic: Optional[str] = None, width: int = 88) -> None:
    """Print a plain-language guide to the functions of Table 1 of the paper.

    Parameters
    ----------
    topic : str, optional
        A stage ("3.3") or a function ("baseline", "lmm.R"). Without it, the whole guide is printed.
    width : int
        Line width of the printed text.

    Examples
    --------
    >>> import pupilread as pr
    >>> pr.guide("baseline")   # one function
    >>> pr.guide("3.4")        # one stage
    >>> pr.guide()             # all stages
    """
    if topic is None:
        out = [_fill(INTRO, width), ""]
        for stage, title, funcs in STAGES:
            out.append(f"{stage} {title}\n")
            out.extend(_format(n, p, width) for n, p in funcs)
        print("\n".join(out).rstrip())
        return
    key = _key(str(topic))
    for stage, title, funcs in STAGES:
        if key == stage:
            print("\n".join([f"{stage} {title}\n"] + [_format(n, p, width) for n, p in funcs]).rstrip())
            return
    for stage, title, name, paras in _entries():
        if key == _key(name):
            print(f"{stage} {title}\n\n{_format(name, paras, width)}".rstrip())
            return
    raise ValueError(f"no guide entry for {topic!r}; topics: {', '.join(topics())}")
