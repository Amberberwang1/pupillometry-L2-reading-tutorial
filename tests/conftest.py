"""Shared fixtures: tiny synthetic trials with known answers, and a small example study written to disk."""
import numpy as np
import pandas as pd
import pytest

import pupilread as pr


def make_samples(n=3000, hz=1000.0, pupil=1000.0, reader="r1", trial=1, version="a", eye="right", gaze=(512.0, 384.0),
                 blink=None, item=None):
    """One trial of ``n`` samples: constant pupil and gaze, optional blink (start, length) in samples."""
    t = np.arange(n) * 1000.0 / hz
    p = np.full(n, float(pupil)) if np.isscalar(pupil) else np.asarray(pupil, float)
    b = np.zeros(n, bool)
    if blink is not None:
        a, ln = blink
        b[a:a + ln] = True
        p = p.copy()
        p[a:a + ln] = np.nan
    df = pd.DataFrame({"reader": reader, "item": item if item is not None else trial, "trial": trial,
                       "version": version, "eye": eye, "time": t, "pupil": p, "gaze_x": gaze[0], "gaze_y": gaze[1],
                       "in_blink": b, "in_saccade": False, "trial_end": t[-1]})
    df.attrs = {"hz": hz, "pupil_unit": "area"}
    return df


def concat(*parts, hz=1000.0):
    out = pd.concat(parts, ignore_index=True)
    out.attrs = {"hz": hz, "pupil_unit": "area"}
    return out


@pytest.fixture
def samples():
    return make_samples


@pytest.fixture(scope="session")
def example(tmp_path_factory):
    folder = tmp_path_factory.mktemp("example")
    return pr.make_example(str(folder / "ex"), n_readers=2, n_items=4, n_lines=8, seed=7)
