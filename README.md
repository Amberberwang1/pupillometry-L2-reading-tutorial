# Supplementary Materials: Pupillometry for L2 Reading Research

## Overview

This repository contains the complete analysis scripts for the preprocessing pipeline described in:

> **Pupillometry for L2 reading research: A step-by-step tutorial for eye-tracking researchers**

All scripts are implemented in Python 3 using standard scientific computing libraries (pandas, NumPy, SciPy, Matplotlib, Seaborn). No specialised pupillometry packages are required.

## Requirements

```
Python >= 3.8
pandas >= 1.3
numpy >= 1.20
scipy >= 1.7
matplotlib >= 3.4
seaborn >= 0.11
```

Install dependencies:
```bash
pip install pandas numpy scipy matplotlib seaborn
```

## Repository Structure

```
supplementary_materials/
├── README.md                          # This file
├── 01_main_pipeline.py                # Core preprocessing pipeline (Sections 3.1–3.6)
├── 02_time_course_visualisation.py    # Time course plots — Figure 3 (Section 3.5)
├── 03_baseline_equivalence_check.py   # Baseline verification (Section 3.3)
├── 04_preprocessing_diagnostics.py    # Diagnostic checks (Section 3.5)
├── 05_comprehension_accuracy.py       # Comprehension scores (Section 5)
└── utils_condition_mapping.py         # Helper: Block B condition labels
```

## Script-to-Section Mapping

| Script | Paper Section | Pipeline Stage | What It Does |
|--------|--------------|----------------|-------------|
| `01_main_pipeline.py` | Section 3.1–3.6 | Stages 1–6 | Runs the full preprocessing pipeline: blink removal, fixation filtering, baseline correction (subtractive, first 500 ms), gaze-position regression, time binning, and fixation-level t-tests |
| `02_time_course_visualisation.py` | Section 3.5 | Stage 5 | Generates Figure 3: baseline-corrected pupil change over time by condition and block, with Gaussian smoothing and 95% confidence intervals |
| `03_baseline_equivalence_check.py` | Section 3.3 | Stage 3 | Tests whether raw baseline pupil sizes differ between conditions within each block (paired t-tests at the participant level) |
| `04_preprocessing_diagnostics.py` | Section 3.5 | Stage 5 | Runs diagnostic checks: blink-related data loss by condition, gaze-position regression variance explained, and participant-level effect consistency |
| `05_comprehension_accuracy.py` | Section 5 | — | Calculates comprehension accuracy by block and condition |
| `utils_condition_mapping.py` | — | — | Helper module that maps Block B file identifiers to experimental conditions (ss/ns) |

## Running the Pipeline

### Step 1: Full preprocessing and analysis

```bash
python 01_main_pipeline.py
```

This script runs all six pipeline stages in sequence and produces:
- `pupillometry_processed_data.csv` — Fixation-level data with all corrections applied
- `pupillometry_trial_level.csv` — Trial-level aggregated measures
- Preprocessing summary figures
- Statistical test results printed to console

### Step 2: Generate Figure 3

```bash
python 02_time_course_visualisation.py
```

Requires `pupillometry_processed_data.csv` from Step 1.

### Step 3: Run diagnostic checks

```bash
python 03_baseline_equivalence_check.py
python 04_preprocessing_diagnostics.py
```

These can be run after Step 1 to verify preprocessing quality.

## Key Parameters

The following parameters are set in `01_main_pipeline.py` and correspond to the decisions described in the paper:

| Parameter | Value | Paper Reference |
|-----------|-------|----------------|
| `BASELINE_WINDOW_MS` | 500 | Section 3.3: in-text baseline (first 500 ms) |
| `MIN_FIXATION_DURATION` | 80 | Section 3.2: fixation filter threshold |
| `MIN_PUPIL_SIZE` | 100 | Section 3.1: implausible value removal |
| `MAX_PUPIL_SIZE` | 10000 | Section 3.1: implausible value removal |
| `TIME_BIN_SIZE` | 5000 | Section 3.5: time bins for visualisation |

## Data Format

The pipeline expects fixation reports exported from SR Research Data Viewer as tab- or comma-separated files containing at minimum:

- `CURRENT_FIX_PUPIL` — Pupil diameter (arbitrary units)
- `CURRENT_FIX_DURATION` — Fixation duration (ms)
- `CURRENT_FIX_START` — Fixation onset time (ms)
- `CURRENT_FIX_X` — Horizontal gaze coordinate (pixels)
- `CURRENT_FIX_Y` — Vertical gaze coordinate (pixels)
- `CURRENT_FIX_BLINK_AROUND` — Blink proximity flag
- `TRIAL_INDEX` — Trial identifier
- `condition` — Experimental condition label

## Adapting for Your Own Study

To apply this pipeline to a new dataset:

1. Export fixation reports from your eye-tracking software with the columns listed above.
2. Modify the file paths and condition mappings in `01_main_pipeline.py`.
3. Adjust `BASELINE_WINDOW_MS` if your baseline window differs.
4. Run the pipeline and inspect the diagnostic outputs before proceeding to analysis.

## Citation

If you use or adapt these scripts, please cite the accompanying paper:

> [Full citation to be added upon publication]

## License

These scripts are provided under the MIT License for research and educational purposes.
