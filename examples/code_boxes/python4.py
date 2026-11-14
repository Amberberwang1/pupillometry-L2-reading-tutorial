steps = pr.saccade_steps(raw, fixations, after=(20, 120), before=100)
slopes = pr.step_slopes(steps, by="eye", method="map")     # error map per eye
print(slopes.round(4))                                     # the map of each eye
corrected = pr.correct_gaze(raw, slopes, method="steps")   # before baseline
# alternative: pr.correct_gaze(raw, layout="layout.csv",
#                              method="geometric")
# or regression: pr.correct_gaze(raw, pr.regression_slopes(raw), method="regression")
corrected = pr.baseline(corrected, window=(0, 200), method="subtractive",
                        scale="reader_mean")
