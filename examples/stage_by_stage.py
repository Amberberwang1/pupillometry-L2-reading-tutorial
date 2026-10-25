"""The pipeline of the paper written out stage by stage, for one reader of the example data."""
import pupilread as pr

info = pr.make_example("pupilread_example")
r = info["readers"][0]

samples = pr.read_eyelink(r["samples"], messages=r["messages"], reader=r["reader"], design=info["design"])  # 3.1
fixations = pr.read_fixations(r["fixations"], messages=r["messages"], reader=r["reader"], design=info["design"])
samples = pr.pad_blinks(samples, pad_ms=100)                       # 3.2: pad blinks, remove invalid samples
samples = pr.interpolate(samples, max_gap_ms=1000)                 # adds pupil_interp (removal stays primary)
loss = pr.data_loss(samples)
print(loss.by_version)
samples, excluded = pr.exclude_trials(samples, min_valid=0.5)
bins = pr.bin(samples, bin_ms=20, min_valid=0.5)                   # 3.1: 20 ms bins
print(pr.compare_levels(samples, fixations).summary)               # fixation reports vs samples
steps = pr.saccade_steps(bins, fixations)                          # 3.4: pupil steps across saccades
slopes = pr.step_slopes(steps, by="eye")
print(slopes)
corrected = pr.correct_gaze(bins, slopes, method="steps")          # an alternative option, before baseline()
bins = pr.baseline(bins, window=(0, 200), method="subtractive")    # 3.3
print(pr.low_baselines(bins, min_pct=60))
trials = pr.trial_means(bins, window=(500, 20000))                 # 3.5: time-matched window
whole = pr.trial_means(bins, window=(500, None))                   # whole trial, for comparison
blinks = pr.event_response(samples, "blink")                       # blink-locked responses (Figure 2D)
fig = pr.plot_grand_mean(bins, min_readers=1)                      # 3.6 (Figure 2B)
fig.savefig("grand_mean.png", dpi=150)
pr.export_for_r(trials, bins, folder="for_R")                      # 3.7: trials.csv, bins.csv and the R scripts
