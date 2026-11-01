trials = pr.trial_means(bins, window=(500, 20000))   # bins of Python 3
# options: window=(500, None) for the whole trial; cut_before_keypress_ms=1000
pr.export_for_r(trials, bins, folder="for_R")        # files for R (reader 01)
