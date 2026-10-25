# pupilread

Pupil-size preprocessing for **passage reading**: blinks, baselines, gaze-position correction, time-matched windows,
event responses and data-quality checks, ending with two files for the statistical models in R (lme4 and mgcv).

pupilread implements the pipeline of the tutorial *Pupillometry in L2 reading research* (stages 3.1 to 3.6). It has one
function per decision, and every default is the paper's primary choice, so calling the functions without arguments
reproduces the paper's pipeline. The models stay in R, because crossed random effects and GAMMs with an AR1 term are
best fitted there; the three R scripts ship with the package.

What it adds for passage reading:

- **step-based gaze correction**: the artifact per pixel of gaze shift, estimated from the immediate step in pupil size
  across each saccade (`saccade_steps`, `step_slopes`, `correct_gaze`);
- **time-matched windows** with a check of the run-up to the end-of-reading key press (`trial_means`);
- the **fixation-versus-sample comparison** (`compare_levels`, `fixation_means`);
- **event responses** locked to blinks, saccades or return sweeps (`event_response`);
- a **table of the trial measure under each option** for a reduced multiverse analysis (`options_table`,
  `multiverse.R`).

Status: 1.0.0, the version the paper describes. Tested on EyeLink 1000 Plus recordings (Data Viewer
reports, 1,000 and 2,000 Hz); other trackers can be read with `read_csv` (column mapping), which has been tested on
synthetic files only.

## Installation

Python 3.9 or later, with numpy, pandas, scipy, matplotlib and PyYAML (installed automatically):

```
pip install pupilread
```

Until the package is on PyPI, install it from a copy of this repository (`pip install .` in its folder, or
`pip install pupilread-1.0.0-py3-none-any.whl`). The R scripts need R with lme4 (trial means) and mgcv (time
course).

## Quick start

```python
import pupilread as pr

pr.make_example("example")                        # synthetic Data Viewer reports of 3 readers (or your own data)
result = pr.run_pipeline("example", {"data": {"design": "example/design.csv",
                                              "exclude": "example/exclusions.csv"}})
```

`run_pipeline` finds the sample, message and fixation reports of every reader, runs stages 3.1 to 3.6 with the
paper's settings and writes `example/pupilread_output/`:

- `for_R/trials.csv`, `for_R/bins.csv`, `for_R/options.csv` and the R scripts (see below);
- `tables/` (data loss per trial and by version, low baselines, trial means, saccade steps, step slopes, event
  responses, the fixation-versus-sample comparison);
- `figures/` (the check plots of stage 3.6 and the grand-mean time course);
- `summary.json` (counts, data loss, exclusions and the settings used).

Then, in R, from `example/pupilread_output/for_R`:

```
Rscript lmm.R          # R 1: trial-level mixed model of the primary measure
Rscript multiverse.R   # the estimate under each option (Table 3 of the paper)
Rscript gamm.R         # R 2: time-course models (about 30 minutes and 6 GB for the paper's data)
```

The same from the command line: `pupilread example example`, then `pupilread run example --config config.yaml`.
`pupilread config` prints every setting with its default (see `examples/config_paper.yaml`).

## Stage by stage

The paper's pipeline written out (Table 1 of the paper), run from the folder that `make_example()` writes. The
code boxes of Section 3 (Python 1 to 4, R 1 and 2) are in `examples/code_boxes/`, exactly as printed, and the tests
run them on the example data.

```python
import pupilread as pr

samples = pr.read_eyelink("01/sample_report.txt", messages="01/message_report.txt",
                          reader="01", design="design.csv")                      # 3.1
fixations = pr.read_fixations("01/fixation_report.txt", messages="01/message_report.txt",
                              reader="01", design="design.csv")
samples = pr.pad_blinks(samples, pad_ms=100)                                        # 3.2
samples = pr.interpolate(samples, max_gap_ms=1000)        # adds pupil_interp; removal stays the default
loss = pr.data_loss(samples)                              # loss.trials, loss.by_version
samples, excluded = pr.exclude_trials(samples, min_valid=0.5)
bins = pr.bin(samples, bin_ms=20, min_valid=0.5)                                    # 3.1
levels = pr.compare_levels(samples, fixations)                                      # 3.1
steps = pr.saccade_steps(bins, fixations)                                           # 3.4
slopes = pr.step_slopes(steps, by="eye")
bins_g = pr.correct_gaze(bins, slopes, method="steps")    # optional; before baseline()
bins = pr.baseline(bins, window=(0, 200), method="subtractive")                     # 3.3
low = pr.low_baselines(bins, min_pct=60)
trials = pr.trial_means(bins, window=(500, 20000))                                  # 3.5
pr.plot_baselines(low); pr.plot_grand_mean(bins)                                    # 3.6
pr.export_for_r(trials, bins, folder="for_R")                                       # 3.7
```

For several readers, `pr.prepare()` runs stages 3.1 to 3.2 for one reader's samples and `pr.PupilData.concat()` joins
them; `pr.analyse()` runs the pooled stages. Gaze correction must come before baseline correction, so that the
baseline is corrected for its own gaze position: `baseline()` and `correct_gaze()` raise a `PipelineOrderWarning`
when they are applied the other way round, and `run_pipeline` keeps the order.

## Functions

Each entry gives the decision the function encodes, its defaults (the paper's primary choices) and the section of the
paper it belongs to. Full docstrings: `help(pr.<function>)` or `docs/reference.md`.

### 3.1 Reading data and data level

- **`read_eyelink(path, messages=None, onset="DISPLAY_target", end="KEYBOARD_endTarget", eye="auto", reader=None, design=None, pupil_unit="area")`**
  reads a Data Viewer sample report into the sample table: one row per sample from text onset to the key press, with
  reader, item, trial, version, eye, time (ms from text onset), pupil, gaze_x, gaze_y, in_blink, in_saccade and
  trial_end. Only the needed columns are read, in chunks, so reports of several gigabytes fit in memory; duplicated
  rows are dropped with a warning. The sampling rate is taken from the time stamps (`attrs["hz"]`), and every
  duration below is in ms, whatever the rate.
- **`read_csv(path, columns, hz=None, missing=0)`** reads any sample-level file with a mapping of our column names to
  the file's (in the spirit of gazeR's `make_gazer()`), the missing-value code(s) and the sampling rate.
- **`read_fixations(path, messages=None, ...)`**, **`read_messages(path)`**, **`read_design(design)`**: fixation and
  message reports, and the design table (trial or item to version, optionally per reader).
- **`to_diameter(data)`**: square root of pupil area, for analyses on the diameter scale (Section 3.3).
- **`bin(samples, bin_ms=20, min_valid=0.5)`**: 20 ms bins; a bin enters the analysis (`ok`) if at least half of its
  samples are valid. Returns one row per trial and bin with sample counts, so that reader means can weight bins.
- **`compare_levels(samples, fixations, min_fix_ms=80)`**: the fixation-report pupil value of every retained fixation
  (at least 80 ms, no adjacent blink) against the mean of the valid samples inside it, and the share of reading time
  that retained fixations cover. **`fixation_means(fixations, reader_means)`** gives the trial measure from fixation
  averages (the fixation option of Table 3).

### 3.2 Blinks and artifacts

- **`pad_blinks(samples, pad_ms=100, pupil_range=(100, 10000))`**: pads every tracker blink by 100 ms on each side and
  sets padded samples and samples outside the plausible range to missing.
- **`detect_blinks(samples, method="speed", mad_k=16, pad_ms=50)`**: pupil-based detection (Kret & Sjak-Shie, 2019)
  for trackers without blink events: implausible values and dilation speeds above the median plus 16 MAD, computed on
  10 ms means, widened by 50 ms. **`detector_agreement(samples)`** compares it with the tracker's padded blinks
  (Supplementary Note S1).
- **`interpolate(samples, max_gap_ms=1000, kind="linear")`**: fills gaps of up to 1 s (linear, or the cubic spline of
  Mathôt et al., 2018) in a separate column, `pupil_interp`; removal stays the primary choice.
- **`data_loss(samples, by="version")`**: per trial the shares of invalid samples, of samples lost to the padding and
  of valid samples, blinks and saccades per second; and their reader means by version.
- **`exclude_trials(samples, min_valid=0.5, exclude=None)`**: drops trials with more than half of their samples
  missing and trials listed for other reasons decided blind to version (for example skimmed texts).

### 3.3 Baseline correction

- **`baseline(bins, window=(0, 200), method="subtractive", scale="reader_mean")`**: change from the trial's baseline
  (0 to 200 ms after text onset, before the light reflex), as a percentage of the reader's mean pupil size; also
  `method="divisive"` or `"none"`, and `scale="baseline_mean"` or `None`. Adds `change`, `baseline` and `baseline_pct`.
- **`low_baselines(bins, min_pct=60)`**: flags trials whose baseline is below 60% of the reader mean; read the cut-off
  from `plot_baselines()` (log-scaled counts).
- **`reader_means(bins)`**: the denominator of the scaling (mean of all valid samples of each reader).

### 3.4 Gaze-position correction

- **`saccade_steps(bins, fixations, after=(20, 120), before=100)`**: for every saccade between two retained fixations,
  the step in pupil size from the 100 ms before saccade onset to 20 to 120 ms after landing, as % of the reader mean,
  with the saccade's size and type (forward, regression, return sweep, vertical).
- **`step_slopes(steps, by="eye", method="joint")`**: the artifact per pixel of gaze shift from a regression of the
  steps on horizontal and vertical saccade size, per eye; also per reader, `method="by_type"` (horizontal slope from
  within-line saccades, vertical slope from vertical saccades; exploratory) and `method="map"` (a piecewise-linear map
  of horizontal position; exploratory).
- **`regression_slopes(bins, time_terms=False)`**: slopes from regressing pupil size on gaze position in the reading
  data (pooled, or within trials with time terms), for comparison.
- **`correct_gaze(bins, slopes, method=None)`**: subtracts the artifact from every 20 ms bin, before
  `baseline()`; `method=None` (the paper's primary estimate) leaves the bins unchanged.

### 3.5 Trial length and events

- **`trial_means(bins, window=(500, 20000), cut_before_keypress_ms=0)`**: one value per trial, the mean change in a
  window with the same start and end in every version (0.5 to 20 s); `window=(500, None)` gives the whole-trial mean,
  and `cut_before_keypress_ms` leaves out the run-up to the key press.
- **`event_response(data, event="blink" | "saccade" | "return_sweep" | table, window=None, by="version")`**:
  event-locked responses with local baselines: blinks locked to their offset with a baseline before the padded blink
  (Figure 2D), return sweeps locked to landing (Figure 2C), or any table of event times. Returns reader means and their
  mean and SEM across readers.

### 3.6 Checks and figures

`plot_trials` (trial overlays), `plot_baselines` (baseline histogram with log counts), `plot_quality` (data loss and
blink and saccade rates by version), `plot_gaze` (gaze position by version) and `plot_grand_mean` (Figure 2B: 1 s
bins, 95% confidence intervals, points with at least 20 readers). All figures are black and white.

### 3.7 Control predictors and the hand-over to R

- **`add_covariates(bins, fixations)`** and **`control_predictors(bins, covariates)`**: trial means adjusted for time,
  gaze position and eccentricity, fixation duration, distance to the next fixation and any study-specific predictor
  (such as local text density), with slopes estimated within trials (Section 3.7).
- **`export_for_r(trials, bins, folder="for_R", bin_ms=100, window=(500, 20000), reference=None)`** writes:
  - `trials.csv`: one row per trial with reader, item, trial, version, `contrast` (0 = reference version, 1 = the
    other), eye, baseline_pct, `change_0_20s` and any option columns;
  - `bins.csv`: one row per trial and 100 ms bin from 0.5 to 20 s with reader, item, trial, version, contrast, time
    (bin centre, s), pupil_change, gaze_x, gaze_y, trial_start and baseline_pct;
  - `options.csv` (for an options table), `pupilread.json` (settings) and copies of the R scripts.

### 5 The estimate under each option

- **`options_table(samples, options=PAPER_OPTIONS)`**: the trial measure under each option, one column per option,
  missing for the trials an option leaves out, with standardised trial-level covariates. Each option changes one
  decision of the primary estimate (`PAPER_OPTIONS` holds those of Tables 3 and S1); `options_spec()` gives the model
  of each column, which `multiverse.R` fits.

## The R scripts

| Script | Paper | Reads | Model |
| --- | --- | --- | --- |
| `lmm.R` | R 1 | `trials.csv` | `change_0_20s ~ contrast + (1 \| reader) + (0 + contrast \| reader) + (1 \| item)`, ML, trials with `baseline_pct >= 60` |
| `multiverse.R` | Table 3 | `trials.csv`, `options.csv` | the same model for every option column (random part, covariates and term from `options.csv`) |
| `gamm.R` | R 2 | `bins.csv` | GAMMs: random intercepts only; per-trial smooths without and with AR1; plus a `te(x, y)` gaze surface |

`pupilread scripts <folder>` copies them anywhere; `MIN_BASE`, `NTHREADS`, `MODELS` and `RANDOM_PART` are read from the
environment.

## Reproducing the paper

`tools/reproduce_paper.py` (in this repository; the released package leaves out `tools/`, including the `--legacy` mode below) reruns the paper's analysis from the raw Data Viewer reports with the package (stage 1 on the
machine that holds the reports, stage 2 with R), fits Tables 3 and S1, recomputes every number quoted in the text and
compares each with the value printed in the paper. With the package's defaults, all of them match
(`docs/reproduction.md`).

The first full-study draft of the paper was computed with earlier scripts. With `prepare --legacy`, the package imposes
three assumptions of those scripts and then reproduces every trial value, every 20 ms bin and every number of that draft
exactly. pupilread corrects them (see `CHANGELOG.md`), which moved the estimates of Table 3 by −0.08 to +0.10
percentage points (primary estimate 1.27% in the draft, 1.37% now):

1. durations counted in samples assumed 1,000 Hz, so 6 of the 45 recordings, made at 2,000 Hz, got 50 ms blink
   padding;
2. the blink padding summed blink flags in 8-bit integers, which overflow where blinks fill more than 127 of the 201
   samples around a sample, so short gaps between blinks stayed valid;
3. one reader's reports listed every row twice, which also doubled that reader's word counts in the screen for skimmed
   texts and excluded five of the reader's trials as read too fast.

## Tests

```
pip install pupilread[test]
pytest
```

The tests use tiny synthetic trials with known answers (a blink of known length is padded to the right length, a
constant pupil gives zero change, a known gaze artifact is recovered from the saccade steps and removed, and so on)
and the synthetic example data, on which they also run the paper's code boxes as printed; the R scripts and boxes are
run when R, lme4 and mgcv are installed.

## Citation and licence

Cite the paper and the archived version of the package (Zenodo DOI to be added at release); `CITATION.cff` has the
details. MIT licence.
