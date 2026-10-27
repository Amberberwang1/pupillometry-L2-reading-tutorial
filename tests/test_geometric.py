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


def test_geometric_scale_recovers_the_scale_of_the_steps():
    rng = np.random.default_rng(3)
    n = 4000
    eye = np.where(np.arange(n) % 2, "left", "right")
    x0, y0 = rng.uniform(50, 950, n), rng.uniform(50, 700, n)
    st = pd.DataFrame({"eye": eye, "type": "forward", "x0": x0, "y0": y0, "x1": x0 + rng.uniform(-300, 300, n),
                       "y1": y0 + rng.uniform(-40, 40, n), "ref": 100.0, "reader": "r1"})
    c0 = pr.foreshortening(st.rename(columns={"x0": "gaze_x", "y0": "gaze_y"}), LAYOUT)
    c1 = pr.foreshortening(st.rename(columns={"x1": "gaze_x", "y1": "gaze_y"}), LAYOUT)
    k_true = np.where(eye == "left", 0.5, -0.3)
    st["step"] = 0.2 + k_true * 100.0 * (c1 / c0 - 1) + rng.normal(0, 0.05, n)
    sc = pr.geometric_scale(st, LAYOUT, by="eye")
    assert sc.loc["left", "k"] == pytest.approx(0.5, abs=0.02) and sc.loc["right", "k"] == pytest.approx(-0.3, abs=0.02)
    assert sc.loc["left", "intercept"] == pytest.approx(0.2, abs=0.01) and (sc["r2"] > 0.9).all()
    assert sc.attrs["method"] == "hybrid" and int(sc["n_saccades"].sum()) == n


@pytest.mark.parametrize("eye", ["left", "right"])
def test_hybrid_correction_removes_a_scaled_artifact(eye):
    s = _trace(eye, "area")
    c = pr.foreshortening(s, LAYOUT)
    s["pupil"] = 1000.0 * c ** 0.5                               # an artifact half the size the model predicts
    b = pr.bin(pr.pad_blinks(s))
    sc = pd.DataFrame({"k": [0.5, 0.5]}, index=["left", "right"])
    g = pr.correct_gaze(b, sc, method="hybrid", layout=LAYOUT)
    ok = b["ok"].to_numpy(bool)
    assert np.allclose(g.loc[ok, "pupil_corrected"], 1000.0) and g.attrs["gaze_correction"] == "hybrid"
    with pytest.raises(ValueError, match="geometric_scale"):
        pr.correct_gaze(b, method="hybrid", layout=LAYOUT)


def test_add_covariates_cos_theta():
    b = pr.bin(pr.pad_blinks(_trace("left", "area")))
    out = pr.add_covariates(b, layout=LAYOUT)
    assert np.allclose(out["cos_theta"], pr.foreshortening(b, LAYOUT), equal_nan=True)
    assert "cos_theta" not in pr.add_covariates(b).columns
    assert pr.CONTROLS_COS_THETA == tuple("cos_theta" if c == "eccentricity" else c for c in pr.CONTROLS)


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


def test_paper_options_include_the_geometric_model_only_with_a_layout(example, tmp_path, recwarn):
    geo = {"gaze_geometric": "3", "gaze_hybrid": "S2", "control_predictors_cos_theta": "S2"}
    cfg = {"data": {"design": example["design"]}, "plots": False}
    res = pr.run_pipeline(example["folder"], cfg, out=str(tmp_path / "a"), verbose=False)
    assert not set(geo) & set(res.options.columns)
    assert not [w for w in recwarn if any(k in str(w.message) for k in geo)]
    res2 = pr.run_pipeline(example["folder"], dict(cfg, gaze={"layout": example["layout"]}), out=str(tmp_path / "b"),
                           verbose=False)
    assert not [w for w in recwarn if any(k in str(w.message) for k in geo)]
    spec = pd.read_csv(tmp_path / "b" / "for_R" / "options.csv")
    for col, table in geo.items():
        assert np.isfinite(res2.options[col]).any()
        assert spec.loc[spec["column"] == col, "table"].astype(str).tolist() == [table]
    cfg3 = dict(cfg, options=None, gaze={"method": "hybrid", "layout": example["layout"]})
    res3 = pr.run_pipeline(example["folder"], cfg3, out=str(tmp_path / "c"), verbose=False)
    assert res3.bins.attrs["baseline"]["column"] == "pupil_corrected" and "k" in res3.slopes.columns
