"""The code boxes of the paper (examples/code_boxes), run as printed on the synthetic example data."""
import os
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

import pupilread as pr

BOXES = os.path.join(os.path.dirname(__file__), os.pardir, "examples", "code_boxes")


def box(name):
    with open(os.path.join(BOXES, name), encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def study(tmp_path_factory):
    folder = tmp_path_factory.mktemp("boxes")
    return pr.make_example(str(folder / "example"), n_readers=4, n_items=4, n_lines=8, seed=11)


def run_in(folder, code, env):
    cwd = os.getcwd()
    os.chdir(folder)
    try:
        exec(compile(code, "<box>", "exec"), env)
    finally:
        os.chdir(cwd)
    return env


def test_python_1_main_stages(study):
    env = run_in(study["folder"], box("python1.py"), {})
    assert {"change_0_20s", "baseline_pct"} <= set(env["trials"].columns)
    assert {"excluded", "reason"} <= set(env["excluded"].columns) and "low" in env["low"].columns
    t, low = env["trials"], env["low"]          # R 1 keeps baseline_pct >= 60: the trials that low leaves unflagged
    assert set(t.loc[t["baseline_pct"] >= 60, "trial"]) == set(low.loc[~low["low"], "trial"]) & set(t["trial"])
    assert env["samples"]["reader"].iat[0] == "01" and set(env["samples"]["version"]) == {"simplified", "non-simplified"}
    out = os.path.join(study["folder"], "for_R")
    assert os.path.exists(os.path.join(out, "trials.csv")) and os.path.exists(os.path.join(out, "bins.csv"))


def test_python_2_to_4_stage_boxes(study):
    folder = study["folder"]
    msg, des = os.path.join(folder, "01", "message_report.txt"), os.path.join(folder, "design.csv")
    env = {"pr": pr, "samples": pr.read_eyelink(os.path.join(folder, "01", "sample_report.txt"), messages=msg, design=des)}
    run_in(folder, box("python2.py"), env)                                     # blinks and exclusions
    assert "valid" in env["samples"].columns and env["loss"].by_version is not None
    run_in(folder, box("python3.py"), env)                                     # bins and baseline
    assert np.isfinite(env["bins"]["change"]).any() and "low" in env["low"].columns
    env4 = {"pr": pr, "samples": env["samples"]}                               # Python 4 starts again from Python 2
    run_in(folder, box("python4.py"), env4)
    assert len(env4["fixations"]) and len(env4["slopes"]) == 1
    b = env4["bins"]
    assert {"pupil_corrected", "change"} <= set(b.columns) and b.attrs["baseline"]["column"] == "pupil_corrected"
    alt = [ln.split("# alternative: ", 1)[1] for ln in box("python4.py").splitlines() if ln.startswith("# alternative: ")]
    env5 = {"pr": pr, "bins": pr.bin(env["samples"], bin_ms=20, min_valid=0.5)}     # the commented alternative line
    run_in(folder, alt[0], env5)
    assert len(alt) == 1 and env5["bins"].attrs["gaze_correction"] == "geometric"
    assert np.isfinite(env5["bins"]["pupil_corrected"]).any()


R_SETUP_1 = "suppressMessages(library(lme4))\n"
R_SETUP_2 = """suppressMessages(library(mgcv))
bins <- read.csv("bins.csv")
bins <- subset(bins, baseline_pct >= 60)
bins$trial <- factor(paste(bins$reader, bins$trial))
bins$reader <- factor(bins$reader); bins$item <- factor(bins$item)
bins$version <- as.ordered(factor(bins$contrast)); contrasts(bins$version) <- "contr.treatment"
bins$trial_start <- bins$trial_start == 1
"""


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="R is not installed")
def test_r_boxes(study, tmp_path):
    chk = subprocess.run(["Rscript", "-e", "library(lme4); library(mgcv)"], capture_output=True)
    if chk.returncode != 0:
        pytest.skip("lme4 or mgcv missing")
    out = tmp_path / "out"
    pr.run_pipeline(study["folder"], {"data": {"design": study["design"]}, "plots": False}, out=str(out), verbose=False)
    fr = out / "for_R"
    (fr / "box_r1.R").write_text(R_SETUP_1 + box("r1.R") + "\ncat('R1 OK', fixef(model)['contrast'], '\\n')\n")
    (fr / "box_r2.R").write_text(R_SETUP_2 + box("r2.R") + "\ncat('R2 OK', coef(model)[2], '\\n')\n")
    for script in ("box_r1.R", "box_r2.R"):
        r = subprocess.run(["Rscript", script], cwd=fr, capture_output=True)
        assert r.returncode == 0, r.stderr.decode()[-2000:]
        assert b"OK" in r.stdout
