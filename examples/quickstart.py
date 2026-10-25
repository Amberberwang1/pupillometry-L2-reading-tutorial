"""Quick start: the whole pipeline on synthetic example data, then the models in R (if installed)."""
import shutil
import subprocess

import pupilread as pr

info = pr.make_example("pupilread_example")              # 3 readers x 4 texts, Data Viewer report format
result = pr.run_pipeline(info["folder"], {"data": {"design": info["design"], "exclude": info["exclusions"]}},
                         out="pupilread_output")
print(result.trials.head())
print(result.options[["reader", "item", "version", "change_0_20s", "whole_trial", "gaze_steps_eye"]].head())

if shutil.which("Rscript"):
    for script in ("lmm.R", "multiverse.R"):
        subprocess.run(["Rscript", script], cwd="pupilread_output/for_R", check=False)
