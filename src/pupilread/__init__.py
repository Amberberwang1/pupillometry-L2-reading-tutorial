"""pupilread: pupillometry preprocessing for passage reading (stages 3.1-3.6 of the tutorial), with R files for the models.

One function per decision, with the paper's primary choice as the default::

    import pupilread as pr
    samples = pr.read_eyelink("samples.txt", messages="messages.txt")
    samples = pr.pad_blinks(samples, pad_ms=100)
    bins = pr.bin(samples, bin_ms=20)
    bins = pr.baseline(bins, window=(0, 200), method="subtractive")
    trials = pr.trial_means(bins, window=(500, 20000))
    pr.export_for_r(trials, bins, folder="for_R")

or the whole sequence with :func:`run_pipeline`.
"""
from ._utils import SAMPLE_COLUMNS, PipelineOrderWarning
from ._version import __version__
from .baseline import baseline, low_baselines, reader_means
from .blinks import (Loss, data_loss, detect_blinks, detector_agreement, exclude_trials, interpolate, pad_blinks,
                     summarise)
from .controls import add_covariates, control_predictors
from .example import make_example
from .export import export_for_r, gamm_bins, r_script_path
from .gaze import (MAP_KNOTS, classify_saccades, correct_gaze, hat_basis, regression_slopes, saccade_steps,
                   step_slopes)
from .io import read_csv, read_design, read_eyelink, read_fixations, read_messages, to_diameter, trial_windows
from .levels import Levels, bin, compare_levels, fixation_means, retained_fixations
from .options import CONTROLS, OPTIONAL_CONTROLS, PAPER_OPTIONS, options_spec, options_table
from .pipeline import (DEFAULTS, PupilData, Result, analyse, default_config_yaml, find_readers, levels_summary,
                       load_config, prepare, prepare_readers, read_reader, run_pipeline, summarise_events)
from .plots import plot_baselines, plot_gaze, plot_grand_mean, plot_quality, plot_trial, plot_overlays
from .windows import Events, event_response, trial_means, window_name

__all__ = [
    "__version__", "SAMPLE_COLUMNS", "PipelineOrderWarning",
    # 3.1 reading data and data level
    "read_eyelink", "read_csv", "read_messages", "read_fixations", "read_design", "trial_windows", "to_diameter",
    "bin", "compare_levels", "retained_fixations", "fixation_means", "Levels",
    # 3.2 blinks and artifacts
    "pad_blinks", "detect_blinks", "detector_agreement", "interpolate", "data_loss", "summarise", "exclude_trials", "Loss",
    # 3.3 baseline
    "reader_means", "baseline", "low_baselines",
    # 3.4 gaze position
    "saccade_steps", "classify_saccades", "step_slopes", "regression_slopes", "correct_gaze", "hat_basis", "MAP_KNOTS",
    # 3.5 trial length and events
    "trial_means", "window_name", "event_response", "Events",
    # 3.6 checks and figures
    "plot_trial", "plot_overlays", "plot_baselines", "plot_grand_mean", "plot_quality", "plot_gaze",
    # 3.7 control predictors and export for R
    "add_covariates", "control_predictors", "export_for_r", "gamm_bins", "r_script_path",
    # 5 options
    "options_table", "options_spec", "PAPER_OPTIONS", "CONTROLS", "OPTIONAL_CONTROLS",
    # pipeline
    "run_pipeline", "prepare", "prepare_readers", "analyse", "find_readers", "read_reader", "load_config",
    "default_config_yaml", "DEFAULTS", "PupilData", "Result", "levels_summary", "summarise_events",
    # example data
    "make_example",
]
