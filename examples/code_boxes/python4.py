fixations = pr.read_fixations("example/01/fixation_report.txt",
                              messages="example/01/message_report.txt",
                              design="example/design.csv")
raw = pr.bin(samples, bin_ms=20, min_valid=0.5)    # samples of Python 2
steps = pr.saccade_steps(raw, fixations, after=(20, 120), before=100)
slopes = pr.step_slopes(steps, by="eye", method="joint")   # % per pixel
corrected = pr.correct_gaze(raw, slopes, method="steps")   # before baseline
# alternative: pr.correct_gaze(raw, layout="example/layout.csv",
#                              method="geometric")
corrected = pr.baseline(corrected, window=(0, 200), method="subtractive")
