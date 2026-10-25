# Changelog

All notable changes to pupilread. The version the paper describes is frozen as 1.0.0; later changes are listed here
so that the paper's numbers can always be reproduced with that version.

## 1.0.0rc1 (release candidate for review)

First release: the pipeline of the tutorial (stages 3.1 to 3.6) as one function per decision, the one-call
`run_pipeline`, `options_table` for the estimate under each option, the export for R and the three R scripts
(`lmm.R`, `gamm.R`, `multiverse.R`).

### Differences from the scripts the paper was first computed with

The package reproduces those scripts exactly when their assumptions are imposed (`tools/reproduce_paper.py
--legacy`). Without them it differs in three ways, each a correction:

- **Sampling rate.** Durations that the scripts counted in samples (blink padding, the interpolation limit, the speed
  filter, the lags of blink-locked responses, the samples a 20 ms bin needs) assumed 1,000 Hz. pupilread reads the
  rate from the time stamps; in the paper's data, 6 of the 45 recordings were made at 2,000 Hz and had received
  50 ms blink padding.
- **Blink padding.** The scripts widened blinks by summing blink flags in 8-bit integers, which overflow inside blinks
  longer than 127 samples and left the middle of such blinks unflagged; where the tracker still reported a pupil
  value there, those samples were kept as valid. pupilread pads every blink completely.
- **Duplicated samples.** One reader's sample report listed every sample twice; pupilread drops such rows with a
  warning.

The corrections moved the estimates of Tables 3 and S1 by at most 0.04 percentage points, except the GAMM with a gaze
surface (2.04% [0.51, 3.58] before, 1.84% [0.31, 3.38] now); the analysed trials fell from 982 to 981 (one more trial
lacks a 0–200 ms baseline). The paper reports the corrected values, and `docs/reproduction.md` lists both sets.
