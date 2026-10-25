# Main stages for one reader of the example data (Sections 3.1-3.7)
import pupilread as pr
samples = pr.read_eyelink("01/sample_report.txt", design="design.csv",
                          messages="01/message_report.txt")
samples = pr.pad_blinks(samples, pad_ms=100)                       # 3.2
samples, excluded = pr.exclude_trials(samples, min_valid=0.5,
                                      exclude="exclusions.csv")    # 3.2
bins = pr.bin(samples, bin_ms=20)                                  # 3.1
bins = pr.baseline(bins, window=(0, 200), method="subtractive")    # 3.3
low = pr.low_baselines(bins, min_pct=60)                           # 3.3
trials = pr.trial_means(bins, window=(500, 20000))                 # 3.5
trials = trials[~trials["trial"].isin(low.loc[low["low"], "trial"])]
pr.export_for_r(trials, bins, folder="for_R")      # files for R 1 and R 2
# pr.run_pipeline() runs the same stages for every reader at once
