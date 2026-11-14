import matplotlib.pyplot as plt
# Check the window: pupil size in the first 2 s after text onset, averaged over all readers and both text versions; the pupil should react to the text only after the window ends
fig = pr.plot_grand_mean(pr.baseline(raw, method="none"), by=None,
                         bin_s=0.02, max_s=2, min_baseline_pct=None)
fig.savefig("check_window.png", dpi=150, bbox_inches="tight")
# Baseline window=(start, end) in ms from text onset; change it if needed
bins = pr.baseline(raw, window=(0, 200), method="subtractive",
                   scale="reader_mean")      # end before the reaction
low = pr.low_baselines(bins, min_pct=60)     # baselines below 60%
fig = pr.plot_baselines(low, min_pct=60)     # histogram to choose the cut-off
fig.savefig("check_baselines.png", dpi=150, bbox_inches="tight")
plt.show()                                   # show both figures
print(low.loc[low["low"], ["reader", "trial", "reason"]])
