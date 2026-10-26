"""Check pupilread's geometric gaze correction against pypillometry 2 for the bins of one reader.

pypillometry (Mittner, 2020), in its development version 2 (2.0a2, https://github.com/ihrke/pypillometry, commit
8cafd9b), computes the foreshortening factor cos(alpha) of Hayes and Petrov (2016): the cosine of the angle between the
eye-to-camera and the eye-to-gaze lines. ``ForeshorteningCalibration.get_correction_factor()`` returns 1 / cos(alpha)
for gaze positions in pixels. This script computes the correction factor of every 20 ms bin of one reader with both
packages and prints the largest difference, for two layouts:

1. The eye faces the centre of the image, which ``get_correction_factor()`` assumes (one eye, no screen offset). Its
   conversion from pixels to mm keeps y pointing down, so the camera position is passed with y pointing down.
2. A general layout (``layout.csv``, or an invented one with the eyes below the centre of the image): gaze converted to
   the eye frame with ``ExperimentalSetup`` (``pixels_to_mm``, then ``screen_point_to_eye_frame`` with y turned to point
   up and the screen offset of the recorded eye), and cos(alpha) from ``_compute_cos_alpha_vectorized``.

Usage: python tools/geometric_vs_pypillometry.py <cache folder of one reader> [layout.csv]
(the cache folder holds the reader's ``pupildata.json`` and ``bins.csv.gz``, as written by ``PupilData.save()``).
"""
import sys

import numpy as np

import pupilread as pr
from pypillometry.eyedata.experimental_setup import ExperimentalSetup
from pypillometry.eyedata.foreshortening_calibration import ForeshorteningCalibration, _compute_cos_alpha_vectorized

GENERAL = {"image_width": 400.0, "image_height": 300.0, "width_px": 1024.0, "height_px": 768.0, "Sx": -200.0,
           "Sy": 100.0, "Sz": 600.0, "Cx": 0.0, "Cy": -170.0, "Cz": 480.0, "eye": "midline", "eye_separation": 64.0}


def mm(v):
    return f"{v} mm"


def calibration(setup, eye):
    """A calibration object with the camera angles of the setup (its spline is not used here)."""
    return ForeshorteningCalibration(eye=eye, theta=setup.theta, phi=setup.phi, experimental_setup=setup,
                                     spline_coeffs=np.ones(4), spline_knots=np.array([0.0] * 4 + [1.0] * 4))


def main(folder, layout_csv=None):
    bins = pr.PupilData.load(folder).bins
    ok = bins["ok"].to_numpy(bool) & bins["gaze_x"].notna().to_numpy() & bins["gaze_y"].notna().to_numpy()
    b = bins[ok].reset_index(drop=True)
    eye = str(b["eye"].iat[0]).lower()
    gx, gy = b["gaze_x"].to_numpy(float), b["gaze_y"].to_numpy(float)
    print(f"reader {b['reader'].iat[0]} ({eye} eye): {len(b)} bins with valid gaze")

    # 1. eye facing the centre of the image
    lay1 = dict(GENERAL, Sx=-200.0, Sy=150.0, eye=eye)
    f_pr = 1.0 / pr.foreshortening(b, lay1)
    setup = ExperimentalSetup(screen_resolution=(1024, 768), physical_screen_size=(mm(400), mm(300)),
                              eye_to_screen_center=mm(600), camera_offset=(mm(0), mm(170), mm(480)))
    f_pp = np.ma.getdata(calibration(setup, eye).get_correction_factor(gx, gy))
    print(f"1. eye facing the image centre: correction factor {f_pr.min():.4f} to {f_pr.max():.4f}; "
          f"largest difference from pypillometry {np.max(np.abs(f_pr - f_pp)):.2e}")

    # 2. general layout, each eye at its own position
    lay2 = pr.read_layout(layout_csv) if layout_csv else GENERAL
    f_pr2 = 1.0 / pr.foreshortening(b, lay2)
    dx = {"left": {"left": 0.0, "right": lay2["eye_separation"]}, "right": {"left": -lay2["eye_separation"], "right": 0.0},
          "midline": {"left": -lay2["eye_separation"] / 2, "right": lay2["eye_separation"] / 2}}[lay2["eye"]][eye]
    W, H = lay2["image_width"], lay2["image_height"]
    delta = (lay2["Sx"] + W / 2 - dx, lay2["Sy"] - H / 2)          # image centre relative to the recorded eye
    setup2 = ExperimentalSetup(screen_resolution=(int(lay2["width_px"]), int(lay2["height_px"])),
                               physical_screen_size=(mm(W), mm(H)), screen_offset=(mm(delta[0]), mm(delta[1])),
                               eye_to_screen_center=mm(float(np.sqrt(lay2["Sz"] ** 2 + delta[0] ** 2 + delta[1] ** 2))),
                               camera_offset=(mm(lay2["Cx"] - dx), mm(lay2["Cy"]), mm(lay2["Cz"])))
    x_mm, y_mm = setup2.pixels_to_mm(gx, gy)                       # centred on the image, y down
    tx, ty, tz = setup2.screen_point_to_eye_frame(x_mm, -y_mm)     # eye frame, y up
    cos_pp = _compute_cos_alpha_vectorized(tx, ty, setup2.theta, setup2.phi, setup2.r, float(np.mean(tz)))
    print(f"2. {'layout.csv' if layout_csv else 'invented general layout'}: correction factor {f_pr2.min():.4f} to "
          f"{f_pr2.max():.4f}; largest difference from pypillometry {np.max(np.abs(f_pr2 - 1.0 / cos_pp)):.2e}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
