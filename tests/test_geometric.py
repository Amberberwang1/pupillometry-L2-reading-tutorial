"""The geometric gaze correction (Hayes & Petrov, 2016): the layout file, cos theta and the corrected trace."""
import numpy as np
import pandas as pd
import pytest

import pupilread as pr
from conftest import make_samples

#: A layout measured from the left eye: 400 x 300 mm image of 1000 x 750 pixels at 600 mm, camera below and in front.
LAYOUT = {"image_width": 400.0, "image_height": 300.0, "width_px": 1000.0, "height_px": 750.0, "Sx": -200.0,
          "Sy": 150.0, "Sz": 600.0, "Cx": 0.0, "Cy": -200.0, "Cz": 500.0, "eye": "left", "eye_separation": 64.0}


def test_cos_theta_known_angles():
    lay = dict(LAYOUT, Cy=0.0)                                   # camera straight ahead of the left eye
    b = pd.DataFrame({"gaze_x": [500.0, 875.0], "gaze_y": [375.0, 375.0], "eye": "left"})
    c = pr.foreshortening(b, lay)                                # 500 px is straight ahead; 875 px is 150 mm right
    assert c[0] == pytest.approx(1.0) and c[1] == pytest.approx(600 / np.hypot(600, 150))


def test_each_eye_uses_its_own_position():
    b = pd.DataFrame({"gaze_x": [300.0, 300.0], "gaze_y": [200.0, 200.0], "eye": ["left", "right"]})
    c = pr.foreshortening(b, LAYOUT)
    right = dict(LAYOUT, Sx=LAYOUT["Sx"] - 64, Cx=LAYOUT["Cx"] - 64)      # the same, seen from the right eye
    assert c[1] == pytest.approx(pr.foreshortening(b.iloc[[0]], right)[0]) and c[0] != pytest.approx(c[1])
    mid = dict(LAYOUT, eye="midline", Sx=LAYOUT["Sx"] - 32, Cx=LAYOUT["Cx"] - 32)   # measured from the midline
    assert np.allclose(pr.foreshortening(b, mid), c)


def _trace(eye, unit):
    """Constant true pupil of 1,000 units, foreshortened by the layout; gaze constant within each 20 ms bin."""
    n = 4000
    k = np.arange(n) // 20
    s = make_samples(n=n, pupil=1.0, eye=eye)
    s["gaze_x"] = 100.0 + (k * 37) % 800
    s["gaze_y"] = 100.0 + (k * 23) % 550
    c = pr.foreshortening(s, LAYOUT)
    s["pupil"] = 1000.0 * (c if unit == "area" else np.sqrt(c))
    s.attrs = {"hz": 1000.0, "pupil_unit": unit}
    return s


@pytest.mark.parametrize("eye", ["left", "right"])
@pytest.mark.parametrize("unit", ["area", "diameter"])
def test_geometric_correction_recovers_the_true_pupil(eye, unit):
    b = pr.bin(pr.pad_blinks(_trace(eye, unit)))
    assert b["pupil"].std() > 10                                 # the artifact is there
    g = pr.correct_gaze(b, layout=LAYOUT, method="geometric")
    ok = b["ok"].to_numpy(bool)
    assert np.allclose(g.loc[ok, "pupil_corrected"], 1000.0) and g.attrs["gaze_correction"] == "geometric"
    assert np.allclose(g["cos_theta"], pr.foreshortening(b, LAYOUT))


def test_read_layout_csv(tmp_path):
    p = tmp_path / "layout.csv"
    rows = [(k, v, "mm") for k, v in LAYOUT.items()]
    pd.DataFrame(rows, columns=["setting", "value", "unit"]).to_csv(p, index=False)
    lay = pr.read_layout(str(p))
    assert lay == LAYOUT
    b = pr.bin(pr.pad_blinks(_trace("left", "area")))
    assert np.allclose(pr.correct_gaze(b, layout=str(p), method="geometric")["pupil_corrected"].dropna(), 1000.0)
    with pytest.raises(ValueError, match="missing setting"):
        pr.read_layout({k: v for k, v in LAYOUT.items() if k != "Cz"})
    with pytest.raises(ValueError, match="unknown setting"):
        pr.read_layout(dict(LAYOUT, camera_z=500))
    with pytest.raises(ValueError, match="needs layout"):
        pr.correct_gaze(b, method="geometric")


def test_geometric_option_and_pipeline(example, tmp_path):
    cfg = {"data": {"design": example["design"]}, "gaze": {"layout": example["layout"]}, "plots": False}
    opts = {"change_0_20s": {}, "geometric": dict(gaze=dict(method="geometric"))}
    res = pr.run_pipeline(example["folder"], dict(cfg, options=opts), out=str(tmp_path / "a"), verbose=False)
    T = res.options
    assert np.isfinite(T["geometric"]).sum() == np.isfinite(T["change_0_20s"]).sum()
    assert not np.allclose(T["geometric"].dropna(), T["change_0_20s"].dropna())
    cfg2 = dict(cfg, options=None, gaze={"method": "geometric", "layout": example["layout"]})
    res2 = pr.run_pipeline(example["folder"], cfg2, out=str(tmp_path / "b"), verbose=False)
    assert res2.bins.attrs["baseline"]["column"] == "pupil_corrected"
