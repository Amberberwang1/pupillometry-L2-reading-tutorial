"""Write docs/reference.md from the docstrings of the public functions (run after changing a docstring)."""
import inspect
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
import pupilread as pr  # noqa: E402

GROUPS = [
    ("3.1 Reading data and data level", ["read_eyelink", "read_csv", "read_fixations", "read_messages", "read_design",
                                         "trial_windows", "to_diameter", "bin", "compare_levels", "retained_fixations",
                                         "fixation_means"]),
    ("3.2 Blinks and artifacts", ["pad_blinks", "detect_blinks", "detector_agreement", "interpolate", "data_loss",
                                  "summarise", "exclude_trials"]),
    ("3.3 Baseline correction", ["reader_means", "baseline", "low_baselines"]),
    ("3.4 Gaze-position correction", ["saccade_steps", "classify_saccades", "step_slopes", "regression_slopes",
                                      "correct_gaze", "hat_basis"]),
    ("3.5 Trial length and events", ["trial_means", "window_name", "event_response"]),
    ("3.6 Checks and figures", ["plot_trial", "plot_trials", "plot_baselines", "plot_grand_mean", "plot_quality", "plot_gaze"]),
    ("3.7 Control predictors and export for R", ["add_covariates", "control_predictors", "export_for_r", "gamm_bins",
                                                 "r_script_path"]),
    ("5 The estimate under each option", ["options_table", "options_spec"]),
    ("Pipeline", ["run_pipeline", "load_config", "default_config_yaml", "find_readers", "read_reader", "prepare",
                  "prepare_readers", "analyse", "levels_summary", "summarise_events", "PupilData"]),
    ("Example data", ["make_example"]),
]

out = [f"# pupilread {pr.__version__}: function reference", "",
       "Generated from the docstrings by `tools/make_reference.py`. Defaults are the paper's primary choices.", ""]
for title, names in GROUPS:
    out += [f"## {title}", ""]
    for n in names:
        obj = getattr(pr, n)
        try:
            sig = str(inspect.signature(obj))
        except (TypeError, ValueError):
            sig = "(...)"
        out += [f"### `{n}{sig}`", "", "```", inspect.cleandoc(obj.__doc__ or ""), "```", ""]
os.makedirs(os.path.join(os.path.dirname(HERE), "docs"), exist_ok=True)
with open(os.path.join(os.path.dirname(HERE), "docs", "reference.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("docs/reference.md written")
