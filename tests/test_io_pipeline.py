import json
import os
import shutil
import subprocess
import warnings

import numpy as np
import pandas as pd
import pytest

import pupilread as pr


def test_read_eyelink_time_origin_and_design(example):
    job = example["readers"][0]
    msg = pr.read_messages(job["messages"])
    s = pr.read_eyelink(job["samples"], messages=msg, reader=job["reader"], design=example["design"])
    assert list(s.columns) == pr.SAMPLE_COLUMNS
    assert s.attrs["hz"] == 1000.0 and s["eye"].iat[0] in ("left", "right")
    first = s.groupby("trial")["time"].min()
    assert (first == 0).all()                                     # time is ms from text onset
    assert (s.groupby("trial")["time"].max() <= s.groupby("trial")["trial_end"].first()).all()
    assert set(s["version"]) == {"simplified", "non-simplified"}
    f = pr.read_fixations(job["fixations"], messages=msg, reader=job["reader"], design=example["design"])
    assert f["start"].min() < 0 < f["start"].max()                # fixations before text onset are negative


def test_read_eyelink_without_message_report(example):
    job = example["readers"][0]
    a = pr.read_eyelink(job["samples"], messages=job["messages"], reader="x")
    b = pr.read_eyelink(job["samples"], reader="x")                # SAMPLE_MESSAGE column
    assert len(a) == len(b) and np.allclose(a["time"], b["time"])


def test_read_eyelink_drops_duplicated_rows(example, tmp_path):
    job = example["readers"][0]
    lines = open(job["samples"]).read().splitlines()
    p = tmp_path / "dup_samples.txt"
    p.write_text("\n".join([lines[0]] + [l for l in lines[1:] for _ in (0, 1)]) + "\n")
    ref = pr.read_eyelink(job["samples"], messages=job["messages"], reader="x")
    with pytest.warns(UserWarning, match="dropped"):
        s = pr.read_eyelink(str(p), messages=job["messages"], reader="x")
    assert len(s) == len(ref)


def test_read_fixations_drops_duplicated_rows(example, tmp_path):
    job = example["readers"][0]
    lines = open(job["fixations"]).read().splitlines()
    p = tmp_path / "dup_fixations.txt"
    p.write_text("\n".join([lines[0]] + [l for l in lines[1:] for _ in (0, 1)]) + "\n")
    ref = pr.read_fixations(job["fixations"], messages=job["messages"], reader="x")
    f = pr.read_fixations(str(p), messages=job["messages"], reader="x")
    assert len(f) == len(ref) and not f.duplicated(["trial", "start", "end"]).any()


def test_read_eyelink_2000_hz(tmp_path):
    rows = ["TRIAL_INDEX\tTIMESTAMP\tTRIAL_START_TIME\tEYE_TRACKED\tRIGHT_PUPIL_SIZE\tRIGHT_GAZE_X\tRIGHT_GAZE_Y\tRIGHT_IN_BLINK\tRIGHT_IN_SACCADE"]
    for i in range(4000):
        rows.append(f"1\t{1000 + i * 0.5}\t1000\tRIGHT\t1500\t500\t300\t0\t0")
    p = tmp_path / "s.txt"
    p.write_text("\n".join(rows) + "\n")
    s = pr.read_eyelink(str(p), reader="x")
    assert s.attrs["hz"] == 2000.0
    assert pr.pad_blinks(s).attrs["hz"] == 2000.0


def test_read_csv_mapping_and_missing(tmp_path):
    d = pd.DataFrame({"pp": "p1", "tr": 1, "ms": np.arange(100) * 2.0, "diam": 3.5, "x": 1.0, "y": 2.0})
    d.loc[5, "diam"] = -1
    p = tmp_path / "t.csv"
    d.to_csv(p, index=False)
    s = pr.read_csv(str(p), {"reader": "pp", "trial": "tr", "time": "ms", "pupil": "diam", "gaze_x": "x", "gaze_y": "y"},
                    missing=[-1, 0])
    assert s.attrs["hz"] == 500.0 and s["pupil"].isna().sum() == 1 and s.attrs["pupil_unit"] == "diameter"
    assert list(s.columns) == pr.SAMPLE_COLUMNS


def test_to_diameter():
    b = pd.DataFrame({"pupil": [4.0, 9.0], "pupil_interp": [16.0, 25.0]})
    b.attrs = {"pupil_unit": "area"}
    d = pr.to_diameter(b)
    assert list(d["pupil"]) == [2.0, 3.0] and list(d["pupil_interp"]) == [4.0, 5.0]
    with pytest.raises(ValueError):
        pr.to_diameter(d)


def test_config_rejects_unknown_settings():
    with pytest.raises(ValueError, match="unknown setting"):
        pr.load_config({"baseline": {"windw": [0, 500]}})
    assert pr.load_config({"baseline": {"window": [0, 500]}})["baseline"]["window"] == [0, 500]


def test_run_pipeline_end_to_end(example, tmp_path):
    out = tmp_path / "out"
    res = pr.run_pipeline(example["folder"], {"data": {"design": example["design"], "exclude": example["exclusions"]}},
                          out=str(out), verbose=False)
    T = pd.read_csv(out / "for_R" / "trials.csv")
    for c in ("reader", "item", "version", "contrast", "eye", "baseline_pct", "change_0_20s"):
        assert c in T.columns
    assert set(T["contrast"]) == {0, 1}
    assert (T.loc[T["version"] == "non-simplified", "contrast"] == 0).all()
    B = pd.read_csv(out / "for_R" / "bins.csv")
    for c in ("reader", "item", "trial", "version", "time", "pupil_change", "gaze_x", "gaze_y", "trial_start"):
        assert c in B.columns
    assert B["time"].min() == pytest.approx(0.55) and B.groupby(["reader", "trial"])["trial_start"].sum().eq(1).all()
    assert (out / "for_R" / "options.csv").exists() and (out / "for_R" / "lmm.R").exists()
    summ = json.load(open(out / "summary.json"))
    assert summ["trials_excluded"] >= 1 and summ["readers"] == 2
    # the options table: the primary column is the trial mean of the analysed trials
    O = res.options
    tm = res.trials.set_index(["reader", "trial"])["change_0_20s"]
    an = O[O["baseline_pct"] >= 60].set_index(["reader", "trial"])["change_0_20s"]
    assert np.allclose(an, tm.reindex(an.index))
    assert O["low_baselines_kept"].notna().sum() >= O["change_0_20s"].notna().sum()


def test_pupildata_round_trip(example, tmp_path):
    cfg = {"data": {"design": example["design"]}}
    job = pr.find_readers(example["folder"], cfg)[0]
    s, f = pr.read_reader(job, cfg)
    p = pr.prepare(s, f, cfg)
    p.save(str(tmp_path / "c"))
    q = pr.PupilData.load(str(tmp_path / "c"))
    assert len(q.bins) == len(p.bins) and q.bins.attrs["samples_per_bin"] == p.bins.attrs["samples_per_bin"]
    assert np.allclose(q.bins["pupil"], p.bins["pupil"], equal_nan=True)


def test_gamm_bins_average_20ms_bins():
    b = pd.DataFrame({"reader": "r", "item": 1, "trial": 1, "version": "a", "eye": "left",
                      "time": np.arange(0, 1000, 20.0), "pupil": 1.0, "n_valid": 20, "ok": True,
                      "change": np.arange(50, dtype=float), "gaze_x": 1.0, "gaze_y": 2.0, "baseline_pct": 100.0})
    b.attrs = {"samples_per_bin": 20}
    g = pr.gamm_bins(b, bin_ms=100, window=(500, 1000))
    assert list(g["time"]) == [0.55, 0.65, 0.75, 0.85, 0.95]
    assert g["pupil_change"].iat[0] == pytest.approx(np.mean([25, 26, 27, 28, 29]))
    assert list(g["trial_start"]) == [1, 0, 0, 0, 0]


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="R is not installed")
def test_r_scripts_run(example, tmp_path):
    out = tmp_path / "out"
    pr.run_pipeline(example["folder"], {"data": {"design": example["design"]}, "plots": False}, out=str(out),
                    verbose=False)
    fr = out / "for_R"
    chk = subprocess.run(["Rscript", "-e", "library(lme4); library(mgcv)"], capture_output=True)
    if chk.returncode != 0:
        pytest.skip("lme4 or mgcv missing")
    for script, args in (("lmm.R", []), ("multiverse.R", []), ("gamm.R", ["bins.csv", "gamm"])):
        env = dict(os.environ, MODELS="M0,M1")
        r = subprocess.run(["Rscript", script] + args, cwd=fr, capture_output=True, env=env)
        assert r.returncode == 0, r.stderr.decode()[-2000:]
    assert (fr / "lmm_results.csv").exists() and (fr / "multiverse_results.csv").exists()
    assert (fr / "gamm" / "gamm_summary.csv").exists()
