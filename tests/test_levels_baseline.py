import warnings

import numpy as np
import pandas as pd
import pytest

import pupilread as pr
from conftest import concat, make_samples


def test_bins_of_a_constant_trace():
    b = pr.bin(pr.pad_blinks(make_samples(n=1000)), bin_ms=20)
    assert len(b) == 50 and (b["pupil"] == 1000).all() and (b["n_valid"] == 20).all() and b["ok"].all()
    assert b["time"].iloc[1] == 20 and b.attrs["samples_per_bin"] == 20


def test_bins_need_half_their_samples():
    s = make_samples(n=1000)
    s.loc[0:10, "pupil"] = np.nan                    # 11 of the first 20 samples missing
    b = pr.bin(pr.pad_blinks(s, pad_ms=0))
    assert not b["ok"].iat[0] and b["ok"].iat[1]


def test_bins_at_2000_hz():
    b = pr.bin(pr.pad_blinks(make_samples(n=2000, hz=2000.0)))
    assert b.attrs["samples_per_bin"] == 40 and len(b) == 50 and (b["n_valid"] == 40).all()


def test_constant_pupil_gives_zero_change():
    b = pr.baseline(pr.bin(pr.pad_blinks(make_samples(n=3000))))
    assert np.allclose(b["change"], 0) and np.allclose(b["baseline_pct"], 100)


def test_change_is_a_percentage_of_the_reader_mean():
    p = np.where(np.arange(4000) >= 1000, 1100.0, 1000.0)    # +100 units from 1 s
    b = pr.baseline(pr.bin(pr.pad_blinks(make_samples(n=4000, pupil=p))), window=(0, 200))
    rm = (1000 * 1000 + 1100 * 3000) / 4000
    late = b[b["time"] >= 1000]
    assert np.allclose(late["change"], 100 * 100 / rm)
    t = pr.trial_means(b, window=(1000, None))
    assert t["change_1s_to_end"].iat[0] == pytest.approx(100 * 100 / rm)
    d = pr.baseline(pr.bin(pr.pad_blinks(make_samples(n=4000, pupil=p))), method="divisive")
    assert np.allclose(d.loc[d["time"] >= 1000, "change"], 10.0)


def test_low_baselines_are_flagged():
    p = np.full(3000, 1000.0)
    p[:200] = 400.0                                          # a squint in the baseline window
    b = pr.baseline(pr.bin(pr.pad_blinks(make_samples(n=3000, pupil=p))))
    lb = pr.low_baselines(b, min_pct=60)
    assert bool(lb["low"].iat[0]) and lb["baseline_pct"].iat[0] < 60


def test_baseline_warns_about_uncorrected_input():
    b = pr.bin(pr.pad_blinks(make_samples(n=2000)))
    b["pupil_corrected"] = b["pupil"]
    with pytest.warns(pr.PipelineOrderWarning):
        pr.baseline(b, column="pupil")


def test_trial_means_window_and_key_press_cut():
    p = np.where(np.arange(25000) >= 23000, 1200.0, 1000.0)      # run-up to the key press in the last 2 s
    b = pr.baseline(pr.bin(pr.pad_blinks(make_samples(n=25000, pupil=p))))
    full = pr.trial_means(b, window=(500, None))["change_whole_trial"].iat[0]
    cut = pr.trial_means(b, window=(500, None), cut_before_keypress_ms=2000)["change_whole_trial_cut2s"].iat[0]
    assert cut == pytest.approx(0, abs=1e-9) and full > 0
    m20 = pr.trial_means(b)
    assert "change_0_20s" in m20.columns and m20["change_0_20s"].iat[0] == pytest.approx(0, abs=1e-9)


def test_compare_levels_agrees_with_samples():
    s = pr.pad_blinks(make_samples(n=2000))
    f = pd.DataFrame({"reader": "r1", "item": 1, "trial": 1, "version": "a", "start": [100.0, 500.0, 900.0],
                      "end": [300.0, 800.0, 950.0], "duration": [200.0, 300.0, 50.0], "x": 500.0, "y": 380.0,
                      "pupil": 1000.0, "blink_around": "NONE", "ia": 1})
    lv = pr.compare_levels(s, f, min_fix_ms=80)
    assert len(lv.fixations) == 2                             # the 50 ms fixation is not retained
    assert np.allclose(lv.fixations["pupil_samples"], 1000)
    assert lv.summary["mean_abs_diff"] == 0


def test_fixation_means():
    f = pd.DataFrame({"reader": "r1", "item": 1, "trial": 1, "version": "a", "start": [0.0, 600.0, 900.0],
                      "end": [150.0, 800.0, 1100.0], "duration": [150.0, 200.0, 200.0], "x": 500.0, "y": 380.0,
                      "pupil": [1000.0, 1100.0, 1300.0], "blink_around": "NONE", "ia": 1})
    t = pr.fixation_means(f, pd.Series({"r1": 1000.0}))
    assert t["change_fixations"].iat[0] == pytest.approx(20.0)
