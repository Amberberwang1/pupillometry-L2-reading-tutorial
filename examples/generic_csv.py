"""Reading a non-EyeLink export with read_csv (here a synthetic file with Tobii-style column names).

read_csv maps your column names to the sample table; pupil-based blink detection replaces tracker blink events.
This route has been tested on synthetic files only.
"""
import numpy as np
import pandas as pd

import pupilread as pr

rng = np.random.default_rng(1)
t = np.arange(0, 25000, 1000 / 120)                                # 120 Hz, 25 s
d = pd.DataFrame({"Participant": "p1", "Trial": 1, "Timestamp_ms": t,
                  "Pupil_diameter_mm": 3.5 + 0.1 * np.sin(t / 3000) + rng.normal(0, 0.01, len(t)),
                  "Gaze_x": 400 + (t % 3000) / 10, "Gaze_y": 300.0, "Validity": 0})
d.loc[(t > 5000) & (t < 5150), ["Pupil_diameter_mm", "Validity"]] = [-1, 4]   # a blink, coded -1
d.to_csv("tobii_like.csv", index=False)

samples = pr.read_csv("tobii_like.csv", {"reader": "Participant", "trial": "Trial", "time": "Timestamp_ms",
                                         "pupil": "Pupil_diameter_mm", "gaze_x": "Gaze_x", "gaze_y": "Gaze_y"},
                      missing=-1, pupil_unit="diameter")
samples = pr.detect_blinks(samples, pupil_range=(1.5, 9))          # flags blinks from the pupil signal
samples = pr.pad_blinks(samples, pad_ms=100, pupil_range=(1.5, 9))
bins = pr.baseline(pr.bin(samples, bin_ms=20))
print(pr.trial_means(bins, window=(500, 20000)))
