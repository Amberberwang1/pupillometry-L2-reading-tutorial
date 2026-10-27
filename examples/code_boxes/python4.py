fixations = pr.read_fixations("01/fixation_report.txt",
                              messages="01/message_report.txt",
                              design="design.csv")
bins = pr.bin(samples, bin_ms=20, min_valid=0.5)   # samples of Python 2
steps = pr.saccade_steps(bins, fixations, after=(20, 120), before=100)
slopes = pr.step_slopes(steps, by="eye", method="joint")   # % per pixel
bins = pr.correct_gaze(bins, slopes, method="steps")   # before baseline
# alternative: bins = pr.correct_gaze(bins, layout="layout.csv", method="geometric")
bins = pr.baseline(bins, window=(0, 200), method="subtractive")
