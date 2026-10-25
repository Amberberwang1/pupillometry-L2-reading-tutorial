steps = pr.saccade_steps(bins, fixations, after=(20, 120), before=100)
slopes = pr.step_slopes(steps, by="eye", method="joint")   # % per pixel
bins = pr.correct_gaze(bins, slopes, method="steps")       # before baseline
