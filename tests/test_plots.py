import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

import pupilread as pr  # noqa: E402
from conftest import concat, make_samples  # noqa: E402


def _trial():
    # pupil 1000 for 2 s, then 1100; one 50 ms blink at 1 s
    p = np.where(np.arange(3000) < 2000, 1000.0, 1100.0)
    return make_samples(n=3000, pupil=p, blink=(1000, 50))


def test_plot_trial_draws_the_four_stages():
    fig = pr.plot_trial(_trial(), trial=1)
    assert len(fig.axes) == 4
    d = fig.trial_data
    assert d["samples"]["blink_pad"].sum() == 50 + 2 * 100          # 100 ms padding on each side
    # reader mean over the valid samples: (1000 * 1750 + 1100 * 1000) / 2750
    assert d["reader_mean"] == pytest.approx(2850000 / 2750)
    b = d["bins"]
    assert np.allclose(b.loc[b["time"] < 200, "change"], 0)       # 0-200 ms baseline
    late = b.loc[b["time"] >= 2000, "change"]
    assert np.allclose(late, 100 * 100 / (2850000 / 2750))


def test_plot_trial_accepts_padded_samples_and_a_given_reader_mean():
    raw = _trial()
    a = pr.plot_trial(raw, trial=1, reader_mean=1000).trial_data["bins"]
    b = pr.plot_trial(pr.pad_blinks(raw, pad_ms=50), trial=1, reader_mean=1000).trial_data["bins"]
    assert np.allclose(a["change"], b["change"], equal_nan=True)      # padded again with pad_ms=100
    assert np.allclose(a.loc[a["time"] >= 2000, "change"], 10.0)


def test_plot_trial_needs_the_reader_when_several_are_given():
    two = concat(make_samples(n=500, reader="r1"), make_samples(n=500, reader="r2"))
    with pytest.raises(ValueError):
        pr.plot_trial(two, trial=1)
    assert len(pr.plot_trial(two, trial=1, reader="r2").axes) == 4
