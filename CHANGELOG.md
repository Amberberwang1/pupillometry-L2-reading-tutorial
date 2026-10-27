# Changelog

All notable changes to pupilread. The version the paper describes is frozen as 1.0.0; later changes are listed here
so that the paper's numbers can always be reproduced with that version.

## 1.0.0

First release: the pipeline of the tutorial (stages 3.1 to 3.6) as one function per decision, the one-call
`run_pipeline`, `options_table` for the estimate under each option, the export for R and the three R scripts
(`lmm.R`, `gamm.R`, `multiverse.R`).

### Changes since the release candidate (1.0.0rc1)

- The code boxes of the paper (`examples/code_boxes/`): Python 1 now drops trials with too few valid samples or listed
  as skimmed (`exclude_trials`, with a comment on the exclusions file) and flags trials with low baselines
  (`low_baselines`), which R 1 drops (`baseline_pct >= 60`), as the primary analysis does; Python 4 reads the fixation
  report itself and starts from uncorrected bins, with the baseline correction after the gaze correction.
- `plot_trial()` draws one trial at four stages of the pipeline: the raw samples, the samples after blink padding
  and removal, the 20 ms bins and the baseline-corrected change (Figure 2 of the paper). Docstrings that cite the
  paper's figures, tables and code boxes follow its numbering (the pupil signals are now Figure 3, the time-course
  difference Figure 4; the gaze-correction approaches are Table 2 and the estimate under each option Table 3; blink
  padding is Python 2, the baseline correction Python 3 and the gaze correction Python 4).
- `correct_gaze(method="geometric", layout=...)` corrects pupil size with the geometric model of Hayes and Petrov
  (2016), from the measured positions of eye, camera and screen (`read_layout`, `foreshortening`): pupil area is
  divided by cos θ at the gaze position of each 20 ms bin (pupil diameter by its square root), with each recorded eye
  at its own position. It is also available in the config (`gaze.method: geometric` with `gaze.layout`) and as the
  option "Geometric model, measured layout" of Table 3 in `PAPER_OPTIONS`, which `options_table` computes when
  `gaze.layout` names a layout and leaves out otherwise. The example data come with an invented `layout.csv`, Python 4
  shows the call as an alternative, `tools/reproduce_paper.py` holds the layout of the paper's recordings and compares
  the artifact it predicts with the saccade steps, and `tools/geometric_vs_pypillometry.py` checks the correction
  against pypillometry 2.
- The README lists the Data Viewer reports and columns the package reads, in a table (Table S1 of the paper).
- The wheel and the source distribution leave out `tools/` (the scripts that reproduce the paper, with their
  `--legacy` mode); they stay in the repository.
- `plot_trials()` is renamed `plot_overlays()`, so that it is not confused with `plot_trial()` (Figure 2 of the paper);
  `run_pipeline()` saves the overlays as `check_overlays.png`.
- Package metadata for the anonymised review: author "pupilread developers", no e-mail address, and project URLs
  pointing to the anonymised repository (the authors' names and the GitHub URL follow in 1.0.1, without code changes).
- `tools/reproduce_paper.py` recomputes the screen for skimmed texts for any reader whose interest-area report repeats
  rows (see below), computes the readers needed for 80% power from d_z as printed and rounds them up to whole readers,
  checks the 95% confidence intervals of the baseline differences, counts the residual downward spikes left after
  blink removal, with the primary estimate after removing them (Section 3.6), and fits the primary estimate without
  the four readers recorded in the tracker's ellipse-fitting pupil mode and after dropping four readers at random
  2,000 times (Table S2 and its note; `tools/random_reader_drops.R`).

### Differences from the scripts the paper was first computed with

The package reproduces those scripts exactly when their assumptions are imposed (`tools/reproduce_paper.py
--legacy`). Without them it differs in three ways, each a correction:

- **Sampling rate.** Durations that the scripts counted in samples (blink padding, the interpolation limit, the speed
  filter, the lags of blink-locked responses, the samples a 20 ms bin needs) assumed 1,000 Hz. pupilread reads the
  rate from the time stamps; in the paper's data, 6 of the 45 recordings were made at 2,000 Hz and had received
  50 ms blink padding.
- **Blink padding.** The scripts widened blinks by summing blink flags in 8-bit integers, which overflow wherever more
  than 127 of the 201 samples centred on a sample lie in blinks. Inside long blinks the pupil was missing anyway, but
  in short gaps between two blinks the overflow left samples unpadded: in the paper's data, 6,373 samples within
  100 ms of a blink stayed valid, in 41 of the 982 trials of the first draft. pupilread pads every blink completely.
- **Duplicated rows.** One reader's reports listed every row twice; pupilread drops repeated samples (with a warning)
  and repeated fixation rows. The repeats had also doubled that reader's word counts in the companion study's screen
  for skimmed texts, so five of the reader's trials crossed the screen's 600 words-per-minute ceiling. Recomputed
  without the repeats, 61 trials (not 66) are excluded as skimmed or incomplete.

The corrections moved the estimates of Table 3 by −0.08 to +0.10 percentage points: the primary estimate rose from
1.27% [−0.28, 2.83] to 1.37% [−0.20, 2.94], and the GAMM with a gaze surface fell from 2.04% [0.51, 3.58] to
1.96% [0.40, 3.52]. The analysed trials rose from 982 to 986 (five trials of that reader return, and one more trial
lacks a 0–200 ms baseline). The paper reports the corrected values, and `docs/reproduction.md` lists both sets.
