import numpy as np
import pandas as pd
import pytest

import pupilread as pr
from pupilread._utils import dilate
from conftest import concat, make_samples


def test_blink_padded_to_the_right_length():
    s = pr.pad_blinks(make_samples(n=2000, blink=(1000, 50)), pad_ms=100)
    assert s["blink_pad"].sum() == 50 + 2 * 100
    assert s["valid"].sum() == 2000 - 250
    assert np.isnan(s.loc[900:1149, "pupil"]).all() and np.isfinite(s.loc[[899, 1150], "pupil"]).all()


def test_padding_counts_time_not_samples():
    s = pr.pad_blinks(make_samples(n=4000, hz=2000.0, blink=(2000, 100)), pad_ms=100)
    assert s["blink_pad"].sum() == 100 + 2 * 200        # 100 ms = 200 samples at 2,000 Hz


def test_long_blinks_are_padded_completely():
    # an 8-bit sum overflows inside blinks longer than 127 samples; the padding must cover the whole blink
    s = make_samples(n=3000, blink=(1000, 400))
    s["pupil"] = 1000.0                                   # a pupil value reported during the blink
    out = pr.pad_blinks(s, pad_ms=100)
    assert out["blink_pad"].sum() == 400 + 200
    assert out.loc[1000:1399, "valid"].sum() == 0
    m = np.zeros(1000, bool)
    m[300:700] = True
    assert dilate(m, 100).sum() == 600


def test_short_gap_between_blinks_is_padded():
    # two blinks 30 samples apart: more than 127 of the 201 samples around the gap lie in blinks, where an 8-bit sum
    # overflows; the gap, with a valid pupil value, must still count as padded
    s = make_samples(n=3000, blink=(1000, 100))
    s.loc[1130:1229, "in_blink"] = True
    s.loc[1130:1229, "pupil"] = np.nan
    out = pr.pad_blinks(s, pad_ms=100)
    assert not out.loc[1100:1129, "valid"].any()
    assert out["blink_pad"].sum() == (1229 + 100) - (1000 - 100) + 1


def test_invalid_range_and_missing():
    s = make_samples(n=100)
    s.loc[10, "pupil"] = 50          # below the range
    s.loc[11, "pupil"] = 20000       # above
    s.loc[12, "pupil"] = np.nan
    out = pr.pad_blinks(s, pad_ms=0)
    assert out["invalid"].sum() == 3 and out["valid"].sum() == 97
    assert out.loc[10, "pupil_raw"] == 50


def test_padding_stays_within_the_trial():
    a = make_samples(n=500, trial=1, blink=(480, 20))
    b = make_samples(n=500, trial=2)
    out = pr.pad_blinks(concat(a, b), pad_ms=100)
    assert out.loc[out["trial"] == 2, "blink_pad"].sum() == 0


def test_interpolation_fills_short_gaps_linearly():
    p = np.linspace(1000, 1100, 1000)
    s = make_samples(n=1000, pupil=p)
    s.loc[400:449, "pupil"] = np.nan                       # 50 ms gap
    s.loc[0:9, "pupil"] = np.nan                           # gap at the start stays missing
    out = pr.interpolate(s, max_gap_ms=1000)
    assert np.allclose(out.loc[400:449, "pupil_interp"], p[400:450])
    assert out.loc[0:9, "pupil_interp"].isna().all()
    assert out.loc[400:449, "pupil"].isna().all()          # the removal trace is kept


def test_interpolation_leaves_long_gaps():
    s = make_samples(n=3000)
    s.loc[500:1700, "pupil"] = np.nan
    out = pr.interpolate(s, max_gap_ms=1000)
    assert out.loc[500:1700, "pupil_interp"].isna().all()


def test_cubic_interpolation_meets_the_edges():
    t = np.arange(2000)
    p = 1000 + 50 * np.sin(t / 300)
    s = make_samples(n=2000, pupil=p)
    s.loc[900:999, "pupil"] = np.nan
    out = pr.interpolate(s, kind="cubic")
    q = out["pupil_interp"].to_numpy()
    assert np.isfinite(q[900:1000]).all()
    assert abs(q[900] - p[899]) < 2 and abs(q[999] - p[1000]) < 2


def test_speed_detector_flags_a_drop():
    p = np.full(3000, 1000.0) + np.random.default_rng(1).normal(0, 1, 3000).round()
    p[1500:1520] = 400.0                                   # a partial blink, not marked by the tracker
    out = pr.detect_blinks(make_samples(n=3000, pupil=p), column="blink_speed")
    assert out.loc[1500:1519, "blink_speed"].all()
    assert out["blink_speed"].mean() < 0.1


def test_data_loss_and_exclusion():
    a = make_samples(n=1000, trial=1, blink=(500, 100))
    b = make_samples(n=1000, trial=2)
    b.loc[0:699, "pupil"] = np.nan                         # 70% missing
    s = pr.pad_blinks(concat(a, b), pad_ms=100)
    loss = pr.data_loss(s, by=None).trials
    t1 = loss[loss["trial"] == 1].iloc[0]
    assert t1["pct_invalid"] == pytest.approx(10.0)
    assert t1["pct_blink_pad"] == pytest.approx(20.0)      # padding outside the blink itself
    assert t1["pct_valid"] == pytest.approx(70.0)
    assert t1["n_blinks"] == 1
    kept, table = pr.exclude_trials(s, min_valid=0.5, exclude=[("r1", 1)])
    assert set(table.loc[table["excluded"], "reason"]) == {"listed", "valid < 50%"}
    assert len(kept) == 0


def test_detector_agreement_runs():
    s = pr.pad_blinks(make_samples(n=3000, blink=(1000, 120)))
    ag = pr.detector_agreement(s)
    assert ag["pct_padded_caught"].iat[0] >= 120 / 320 * 100 - 1e-9
