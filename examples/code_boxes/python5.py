# bins of Python 3; the window ends at 20 s or 3 s before the key press
trials = pr.trial_means(bins, window=(500, 20000), cut_before_keypress_ms=3000)
# Checks: the same window without the cut, and the whole trial
no_cut = pr.trial_means(bins, window=(500, 20000), cut_before_keypress_ms=0)
whole = pr.trial_means(bins, window=(500, None), cut_before_keypress_ms=0)
# files for R 1 and R 2, with the same cut
pr.export_for_r(trials, bins, folder="for_R", cut_before_keypress_ms=3000)
