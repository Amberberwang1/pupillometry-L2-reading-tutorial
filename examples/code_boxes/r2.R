# bins: 100 ms bins from pr.export_for_r(), trials with baseline_pct >= 60
# reader, item, trial: factors (trial: one level per reader and trial)
# version: ordered factor of contrast (treatment contrasts); contrast 0/1
# trial_start: TRUE in the first bin of each trial (AR1 restarts there)
f <- pupil_change ~ version + s(time, k = 20) +
  s(time, by = version, k = 20) + s(time, trial, bs = "fs", m = 1, k = 3) +
  s(reader, bs = "re") + s(reader, contrast, bs = "re") +
  s(item, bs = "re")
no_ar1 <- bam(f, data = bins, method = "fREML", discrete = TRUE)
rho <- acf(resid(no_ar1), plot = FALSE)$acf[2]  # lag-1 autocorrelation
model <- bam(f, data = bins, method = "fREML", discrete = TRUE,
             rho = rho, AR.start = bins$trial_start)
