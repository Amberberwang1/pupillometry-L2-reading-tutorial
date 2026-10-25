import numpy as np
import pandas as pd
import pytest

import pupilread as pr
from conftest import make_samples

AX = -0.0002          # artifact: share of pupil size per pixel of horizontal gaze offset


def reading_trial(n_fix=60, hz=1000.0, effort=0.0):
    """Fixations along lines of text; measured pupil = true pupil x (1 + AX * (x - 512)), changing at once."""
    rng = np.random.default_rng(3)
    fix, t, x, y = [], 600.0, 150.0, 200.0
    rows = []
    for i in range(n_fix):
        d = 250.0
        fix.append((t, t + d, x, y))
        t += d + 30
        if x > 800:
            x, y = 150.0, y + 48
        else:
            x += 80 + rng.normal(0, 5)
    n = int((t + 1500) * hz / 1000)
    tt = np.arange(n) * 1000 / hz
    gx = np.full(n, fix[0][2])
    gy = np.full(n, fix[0][3])
    for a, b, fx, fy in fix:
        m = (tt >= a) & (tt < b)
        gx[m], gy[m] = fx, fy
    for (a0, b0, x0, y0), (a1, b1, x1, y1) in zip(fix[:-1], fix[1:]):
        m = (tt >= b0) & (tt < a1)
        gx[m], gy[m] = x1, y1                  # the eye has moved by the next sample after the saccade
    gx[tt >= fix[-1][1]] = fix[-1][2]
    true = 1000.0 * (1 + effort)
    pupil = true * (1 + AX * (gx - 512))
    s = make_samples(n=n, hz=hz, pupil=pupil)
    s["gaze_x"], s["gaze_y"] = gx, gy
    F = pd.DataFrame({"reader": "r1", "item": 1, "trial": 1, "version": "a",
                      "start": [f[0] for f in fix], "end": [f[1] for f in fix], "duration": [f[1] - f[0] for f in fix],
                      "x": [f[2] for f in fix], "y": [f[3] for f in fix], "pupil": np.nan, "blink_around": "NONE",
                      "ia": 1})
    return s, F


def test_classify_saccades():
    t = pr.classify_saccades([80, -50, -600, 0, 400], [0, 2, 48, 48, 0])
    assert list(t) == ["forward", "regression", "return sweep", "vertical", "other"]


def test_saccade_steps_recover_the_artifact():
    s, F = reading_trial()
    b = pr.bin(pr.pad_blinks(s))
    st = pr.saccade_steps(b, F)
    assert (st["type"] == "return sweep").any() and (st["type"] == "forward").any()
    sl = pr.step_slopes(st, by=None)
    rm = pr.reader_means(b)["r1"]
    assert sl["bX"].iat[0] == pytest.approx(100 * AX * 1000 / rm, rel=0.02)
    assert abs(sl["bY"].iat[0]) < 0.002


def test_step_correction_flattens_the_trace():
    s, F = reading_trial()
    b = pr.bin(pr.pad_blinks(s))
    sl = pr.step_slopes(pr.saccade_steps(b, F), by=None)
    c = pr.correct_gaze(b, sl, method="steps", by=None)
    v = c.loc[c["ok"], "pupil_corrected"]
    raw = b.loc[b["ok"], "pupil"]
    assert v.std() < 0.1 * raw.std()
    with pytest.warns(pr.PipelineOrderWarning):
        pr.correct_gaze(pr.baseline(b), sl, method="steps", by=None)


def test_regression_slopes_without_time_confound():
    s, F = reading_trial()
    b = pr.bin(pr.pad_blinks(s))
    sl = pr.regression_slopes(b, min_baseline_pct=0)
    assert sl["bX"] == pytest.approx(1000 * AX, rel=0.05)


def test_correction_runs_before_baseline_in_trial_means():
    s, F = reading_trial()
    b = pr.bin(pr.pad_blinks(s))
    sl = pr.step_slopes(pr.saccade_steps(b, F), by=None)
    raw = pr.trial_means(pr.baseline(b), window=(500, None))["change_whole_trial"].iat[0]
    cor = pr.trial_means(pr.baseline(pr.correct_gaze(b, sl, method="steps", by=None)), window=(500, None))
    assert abs(cor["change_whole_trial"].iat[0]) < 0.2 * abs(raw)


def test_blink_locked_response():
    n = 20000
    p = np.full(n, 1000.0)
    blinks = [3000, 9000, 15000]
    for a in blinks:
        p[a + 150:a + 1150] += 30.0                     # a response of +30 units after each blink
    s = make_samples(n=n, pupil=p)
    for a in blinks:
        s.loc[a:a + 149, "in_blink"] = True
        s.loc[a:a + 149, "pupil"] = np.nan
    s = pr.pad_blinks(s, pad_ms=100)
    ev = pr.event_response(s, "blink", window=(-200, 2000), by=None)
    z = ev.summary.set_index("lag")
    assert z.loc[500, "pooled"] == pytest.approx(30.0)
    assert z.loc[1500, "pooled"] == pytest.approx(0.0)
    assert z["n_events"].iat[0] == 3


def test_event_lags_share_a_time_axis_across_rates():
    s1 = pr.pad_blinks(make_samples(n=10000, hz=1000.0, blink=(4000, 150)))
    s2 = pr.pad_blinks(make_samples(n=20000, hz=2000.0, blink=(8000, 300), reader="r2"))
    e1 = pr.event_response(s1, "blink", by=None).by_reader
    e2 = pr.event_response(s2, "blink", by=None).by_reader
    assert np.allclose(e2["lag"] % 1, 0) and np.allclose(e1["lag"] % 1, 0)       # both on a 1 ms grid
    assert e2["lag"].max() == e1["lag"].max() == 2000 and abs(e2["lag"].min() - e1["lag"].min()) <= 1
