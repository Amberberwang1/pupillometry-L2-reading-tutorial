# pupilread

pupilread is a Python package for preprocessing pupil-size data recorded during passage reading. It implements the
pipeline of the paper *Pupillometry for L2 reading research: A step-by-step tutorial for eye-tracking researchers*.
Its defaults reproduce the paper's main analysis.

## Install

Python 3.9 or later:

```
pip install https://github.com/Amberberwang1/pupillometry-L2-reading-tutorial/archive/refs/tags/v1.1.2.zip
```

The statistical models run in R and need the packages lme4 and mgcv.

## Reproduce the paper

1. Download `pupilread_paper_data.zip` (388 MB) from the
   [v1.1.2 release](https://github.com/Amberberwang1/pupillometry-L2-reading-tutorial/releases/tag/v1.1.2) and unzip it.
2. Run the paper's code boxes, `examples/code_boxes/python1.py` to `python5.py`, in order, from the unzipped folder.
3. Python 5 writes a folder `for_R` with the data and the R scripts. In R, run `lmm.R` for the trial means and
   `gamm.R` for the time course.

The `reproduce/` folder in the zip holds the scripts for every number, table and figure in the paper.

## The pipeline

| Stage (paper section) | Functions |
| --- | --- |
| 3.1 Data level | `read_eyelink()`, `read_fixations()`, `compare_levels()` |
| 3.2 Blinks and artifacts | `detect_blinks()`, `pad_blinks()`, `interpolate()`, `exclude_trials()` |
| 3.3 Binning and baseline | `bin()`, `baseline()`, `low_baselines()`, `plot_trial()` |
| 3.4 Gaze position | `saccade_steps()`, `step_slopes()`, `regression_slopes()`, `correct_gaze()` |
| 3.5 Analysis window | `trial_means()`, `event_response()` |
| 3.6 Quality checks | `data_loss()`, `plot_overlays()`, `plot_baselines()`, `plot_grand_mean()`, `plot_quality()`, `plot_gaze()` |
| 3.7 Modelling | `export_for_r()`, with `lmm.R` and `gamm.R` |
| 3.8 Each decision | `options_table()`, with `multiverse.R` |

`pr.guide("baseline")` explains a function in plain language, and `pr.guide("3.3")` explains a whole stage.
`pr.make_example("example")` writes a small simulated data set for a first test.

## Your own data

pupilread reads three Data Viewer reports per reader (sample, message and fixation reports) and a design file that
gives the version of each trial. For other eye trackers, `read_csv()` reads any file with one row per sample, and
`detect_blinks()` finds blinks when the tracker does not mark them. The package was tested on EyeLink 1000 Plus data.

## Citation and licence

Please cite the paper and pupilread 1.1.2 (see `CITATION.cff`). The code is under the MIT licence; the paper's data
are under CC BY 4.0.
