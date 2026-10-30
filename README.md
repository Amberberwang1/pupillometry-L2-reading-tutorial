# pupilread

Pupil-size preprocessing for **passage reading**: blinks, baselines, gaze-position correction, time-matched windows,
event responses and data-quality checks, ending with two files for the statistical models in R (lme4 and mgcv).

pupilread implements the pipeline of the paper *Pupillometry for L2 reading research: A step-by-step tutorial for
eye-tracking researchers* (stages 3.1 to 3.6). It has one
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
reports, 1,000 and 2,000 Hz). Other trackers: see [Other eye trackers](#other-eye-trackers), tested on synthetic
files only.

## In this repository

| Folder | What it holds |
| --- | --- |
| `src/pupilread/` | The package, with the R scripts `lmm.R`, `gamm.R` and `multiverse.R` |
| `examples/` | The paper's code boxes (Python 1 to 5, R 1 and R 2), exactly as printed, and the settings file for `run_pipeline` (`config_paper.yaml`) |

## Installation

Python 3.9 or later, with numpy, pandas, scipy, matplotlib and PyYAML (installed automatically):

```
pip install git+https://github.com/Amberberwang1/pupillometry-L2-reading-tutorial@v1.0.0
```

This installs version 1.0.0, the version the paper describes, and needs git. In a downloaded copy of this repository,
`pip install .` does the same. The R scripts need R with lme4 (trial means) and mgcv (time course). To run pupilread
from R, see [Using pupilread from R](#using-pupilread-from-r).

## What to export from Data Viewer

Three reports per reader, as the tab-separated text files Data Viewer writes (Table S1 of the paper). Reports with all
their columns work as well; only these are read:

| Report | Columns | Used for |
| --- | --- | --- |
| Sample report | TRIAL_INDEX, TIMESTAMP, TRIAL_START_TIME, EYE_TRACKED and, for the recorded eye (LEFT_ or RIGHT_), PUPIL_SIZE, GAZE_X, GAZE_Y, IN_BLINK and IN_SACCADE | Pupil size and gaze at every sample; TRIAL_START_TIME places the messages in time |
| Message report | TRIAL_INDEX, CURRENT_MSG_TEXT, CURRENT_MSG_TIME | Text onset and the end-of-reading key press: `onset` and `end` name the two messages (`DISPLAY_target` and `KEYBOARD_endTarget` in the paper's study) |
| Fixation report | TRIAL_INDEX and, with the prefix CURRENT_FIX_, START, END, DURATION, PUPIL, X, Y and BLINK_AROUND | Comparison of data levels (Section 3.1) and the saccade steps (Section 3.4) |

A design file (`design.csv`) gives the item and version of each trial. `make_example()` writes all four in the layout
the examples use: `01/sample_report.txt`, `01/message_report.txt`, `01/fixation_report.txt` and `design.csv`.

## Other eye trackers

Tested on synthetic files only: the example data, rewritten with other column names, give the same results by this
route as from the Data Viewer reports.

**Samples.** `read_csv()` reads a file with one row per sample, given a mapping of pupilread's column names to the
file's. `time` and `pupil` are required. `onset` names a column with the time of text onset in each trial (or gives a
constant), so that time runs from text onset, and `missing` is the code for missing pupil size:

```python
import pandas as pd
import pupilread as pr

samples = pr.read_csv("P01_samples.csv", design="design.csv", onset="TrialOnset", missing=0,
                      pupil_unit="area",
                      columns={"reader": "Participant", "trial": "Trial", "time": "Timestamp",
                               "pupil": "Pupil", "gaze_x": "GazeX", "gaze_y": "GazeY",
                               "in_blink": "Blink", "in_saccade": "Saccade"})
```

Without a `trial_end` column, each trial ends at its last sample. For trackers without blink events, `detect_blinks()`
flags blinks from the pupil signal.

**Fixations.** The fixation-based steps (`compare_levels`, `saccade_steps`, return sweeps in `event_response` and
`add_covariates`) take a table with one row per fixation. For other trackers, build it from their fixation export:

```python
f = pd.read_csv("P01_fixations.csv")
fixations = pd.DataFrame({"reader": f["Participant"], "trial": f["Trial"],
                          "start": f["Start"] - f["TrialOnset"], "end": f["End"] - f["TrialOnset"],
                          "duration": f["Duration"], "x": f["X"], "y": f["Y"], "pupil": f["Pupil"],
                          "blink_around": f["BlinkAround"]})
```

| Column | Content |
| --- | --- |
| reader, trial | As in the samples |
| start, end, duration | In ms; start and end from text onset |
| x, y | Fixation position in screen pixels |
| pupil | Mean pupil size in the fixation (needed only by `compare_levels` and `fixation_means`) |
| blink_around | Optional: NONE, BEFORE, AFTER or BOTH. Fixations next to a blink are left out, as in the paper; without this column, none are |

Saccade types (forward, regression, return sweep) are set by size thresholds for the paper's layout (20-point text,
48-pixel lines; `classify_saccades`). For another layout, pass your own function to `saccade_steps(..., classify=...)`.

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

## Using pupilread from R

The R package reticulate runs pupilread from R, so the whole analysis can stay in one R session. Once, to install
pupilread in its own Python environment (this needs Python 3.9 or later; `reticulate::install_python()` installs it):

```r
install.packages("reticulate")
reticulate::virtualenv_create("pupilread")
reticulate::virtualenv_install("pupilread",
  "git+https://github.com/Amberberwang1/pupillometry-L2-reading-tutorial@v1.0.0")
```

Then, in each session:

```r
library(reticulate)
use_virtualenv("pupilread")
pr <- import("pupilread", convert = FALSE)

pr$make_example("example")
result <- pr$run_pipeline("example", list(data = list(design = "example/design.csv",
                                                     exclude = "example/exclusions.csv")))
source("example/pupilread_output/for_R/lmm.R", chdir = TRUE)   # R 1
```

In R, `pr.` becomes `pr$` and a pair such as `(0, 500)` becomes `c(0, 500)`: `pr$baseline(bins, window = c(0, 500))`.
`convert = FALSE` keeps each table in Python between stages, together with the settings that later stages use and
`export_for_r()` records; `py_to_r()` turns a table into an R data frame (with pandas 3, this needs reticulate 1.45 or
later). A function that returns two tables, such as `exclude_trials()`, returns them as `out[0]` and `out[1]`.

## The paper's code boxes

`examples/code_boxes/` holds the seven code boxes of the paper (Python 1 to 5, R 1 and R 2) exactly as printed. Run the
Python boxes in order, in one session: Python 1 writes the example data into `example/` and runs `run_pipeline`;
Python 2 to 5 then go through the stages for reader 01. For several readers, `pr.prepare()` runs stages 3.1 and 3.2 for one
reader's samples, `pr.PupilData.concat()` joins them and `pr.analyse()` runs the pooled stages. Gaze correction must
come before baseline correction, so that the baseline is corrected for its own gaze position: `baseline()` and
`correct_gaze()` raise a `PipelineOrderWarning` when they are applied the other way round, and `run_pipeline` keeps
the order.

## Functions

Each entry gives the decision the function encodes, its defaults (the paper's primary choices) and the section of the
paper it belongs to. Full docstrings: `help(pr.<function>)`. `pr.guide()` explains the functions of Table 1 of the
paper in plain language, by stage (`pr.guide("3.3")`) or one at a time (`pr.guide("baseline")`); from the command
line, `pupilread guide baseline`.

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
  `baseline()`; `method=None` (the paper's primary estimate) leaves the bins unchanged. With
  `method="geometric"` and `layout="layout.csv"`, it divides pupil area by cos θ, the foreshortening of the pupil at
  each bin's gaze position predicted from the measured layout (Hayes & Petrov, 2016), or pupil diameter by its square
  root; no slopes are needed. With `method="hybrid"` (exploratory) and the scale factors of `geometric_scale()`, it
  divides by cos θ to the power of each eye's scale factor.
- **`geometric_scale(steps, layout, by="eye")`** (exploratory): the scale factor of the geometric model per eye (or
  reader), from regressing the measured saccade steps on the steps the model predicts: 1 where the steps follow the
  model, 0 where they show no foreshortening artifact, negative where they run against it.
- **`read_layout(layout)`** and **`foreshortening(bins, layout)`**: the measured layout and cos θ, the cosine of the
  angle between the lines from the recorded eye to the camera lens and to the gaze position. The layout file has the
  columns `setting` and `value`, in mm, centred on the eye the positions were measured from (x to the right, y up,
  z towards the screen):

  | setting | value |
  | --- | --- |
  | `image_width`, `image_height` | size of the visible image (mm) |
  | `width_px`, `height_px` | size of the image in pixels |
  | `Sx`, `Sy` | upper-left corner of the image relative to the eye |
  | `Sz` | eye to screen |
  | `Cx`, `Cy`, `Cz` | centre of the camera lens relative to the eye |
  | `eye` | `left` (default), `right` or `midline`: where the positions were measured from |
  | `eye_separation` | distance between the eyes (default 64 mm); each recorded eye is placed at its own position |

### 3.5 Trial length and events

- **`trial_means(bins, window=(500, 20000), cut_before_keypress_ms=0)`**: one value per trial, the mean change in a
  window with the same start and end in every version (0.5 to 20 s); `window=(500, None)` gives the whole-trial mean,
  and `cut_before_keypress_ms` leaves out the run-up to the key press.
- **`event_response(data, event="blink" | "saccade" | "return_sweep" | table, window=None, by="version")`**:
  event-locked responses with local baselines: blinks locked to their offset with a baseline before the padded blink
  (Figure 3D), return sweeps locked to landing (Figure 3C), or any table of event times. Returns reader means and their
  mean and SEM across readers.

### 3.6 Checks and figures

`plot_trial` (one trial at four stages: raw samples, blinks padded and removed, 20 ms bins and the baseline-corrected
change; Figure 2), `plot_overlays` (trial overlays), `plot_baselines` (baseline histogram with log counts), `plot_quality`
(data loss and blink and saccade rates by version), `plot_gaze` (gaze position by version) and `plot_grand_mean`
(Figure 3B: 1 s bins, 95% confidence intervals, points with at least 20 readers). All figures are black and white.

### 3.7 Control predictors and the hand-over to R

- **`add_covariates(bins, fixations)`** and **`control_predictors(bins, covariates)`**: trial means adjusted for time,
  gaze position and eccentricity, fixation duration, distance to the next fixation and any study-specific predictor
  (such as local text density), with slopes estimated within trials (Section 3.7). With a measured layout
  (`add_covariates(bins, fixations, layout="layout.csv")`), `add_covariates` also adds `cos_theta`, the
  foreshortening of the geometric model at each bin's gaze position, which can replace eccentricity
  (`CONTROLS_COS_THETA`).
- **`export_for_r(trials, bins, folder="for_R", bin_ms=100, window=(500, 20000), reference=None)`** writes:
  - `trials.csv`: one row per trial with reader, item, trial, version, `contrast` (0 = reference version, 1 = the
    other), eye, baseline_pct, `change_0_20s` and any option columns;
  - `bins.csv`: one row per trial and 100 ms bin from 0.5 to 20 s with reader, item, trial, version, contrast, time
    (bin centre, s), pupil_change, gaze_x, gaze_y, trial_start and baseline_pct;
  - `options.csv` (for an options table), `pupilread.json` (settings) and copies of the R scripts.

### 5 The estimate under each option

- **`options_table(samples, options=PAPER_OPTIONS)`**: the trial measure under each option, one column per option,
  missing for the trials an option leaves out, with standardised trial-level covariates. Each option changes one
  decision of the primary estimate (`PAPER_OPTIONS` holds those of Tables 3 and S2; the three options of the
  geometric model, in Table 3 and, scaled to the saccade steps or as the control predictor cos θ, in Table S2, are
  included when `gaze.layout` names a measured layout); `options_spec()` gives the model of each column, which
  `multiverse.R` fits.

## The R scripts

| Script | Paper | Reads | Model |
| --- | --- | --- | --- |
| `lmm.R` | R 1 | `trials.csv` | `change_0_20s ~ contrast + (1 \| reader) + (0 + contrast \| reader) + (1 \| item)`, ML, trials with `baseline_pct >= 60` |
| `multiverse.R` | Table 3 | `trials.csv`, `options.csv` | the same model for every option column (random part, covariates and term from `options.csv`) |
| `gamm.R` | R 2 | `bins.csv` | GAMMs: random intercepts only; per-trial smooths without and with AR1; plus a `te(x, y)` gaze surface |

`pupilread scripts <folder>` copies them anywhere; `MIN_BASE`, `NTHREADS`, `MODELS` and `RANDOM_PART` are read from the
environment.

## Citation and licence

Cite the paper and this version of the package (1.0.0); `CITATION.cff` has the details. MIT licence.
