bins = pr.bin(samples, bin_ms=20, min_valid=0.5)       # 20 ms bins
bins = pr.baseline(bins, window=(0, 200), method="subtractive",
                   scale="reader_mean")      # option: window=(0, 500)
low = pr.low_baselines(bins, min_pct=60)     # baselines below 60%
