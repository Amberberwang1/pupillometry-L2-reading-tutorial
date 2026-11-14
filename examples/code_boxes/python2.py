# For every reader in the unzipped pupilread_paper_data folder: read the reports, mark blinks and exclude trials (about 3 min).
# 20 ms averages (bins, Section 3.3) are kept, because the sample reports hold every sample and together can exceed the memory of a computer
import pandas as pd
loss, excluded, raw, fixations = [], [], [], []
for r in pr.find_readers("readers"):            # report files per reader
    s = pr.read_eyelink(r["samples"], messages=r["messages"],
                        design="design.csv", reader=r["reader"])
    # option: s = pr.detect_blinks(s)            # no blink events
    s = pr.pad_blinks(s, pad_ms=100, pupil_range=(100, 10000),
                      speed_filter=True)        # + speed filter
    s, ex = pr.exclude_trials(s, min_valid=0.5, exclude="exclusions.csv")
    # option: s = pr.interpolate(s, max_gap_ms=1000)
    loss.append(pr.data_loss(s, by=None).trials)            # kept trials
    excluded.append(ex)
    raw.append(pr.bin(s, bin_ms=20, min_valid=0.5))         # 20 ms bins
    fixations.append(pr.read_fixations(r["fixations"], messages=r["messages"],
                                       design="design.csv", reader=r["reader"]))
loss, excluded = pd.concat(loss), pd.concat(excluded)
raw, fixations = pd.concat(raw), pd.concat(fixations)
table = pr.summarise(loss, by="version")          # data loss per version
print(table[["measure", "non-simplified", "simplified", "p"]].round(2))
print(excluded.loc[excluded["excluded"], "reason"].value_counts())
