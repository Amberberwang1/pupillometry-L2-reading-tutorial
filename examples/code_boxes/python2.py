samples = pr.read_eyelink("readers/01/sample_report.txt",          # reader 01
                          messages="readers/01/message_report.txt",
                          design="design.csv", reader="01")
samples = pr.pad_blinks(samples, pad_ms=100, pupil_range=(100, 10000))
loss = pr.data_loss(samples, by="version")        # data loss per version
samples, excluded = pr.exclude_trials(samples, min_valid=0.5,
                                      exclude="exclusions.csv")
# option: samples = pr.interpolate(samples, max_gap_ms=1000)
