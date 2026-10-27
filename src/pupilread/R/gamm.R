# R 2. Time-course models (GAMMs) of the pupil trace (Section 3.7 of the tutorial), with mgcv::bam.
# Reads bins.csv written by pupilread.export_for_r(): one row per trial and 100 ms bin from 0.5 to 20 s with reader,
# item, trial, contrast (1 = the version compared with the reference version), time (bin centre, s), pupil_change
# (% of the reader mean), gaze_x and gaze_y (px) and baseline_pct. Trials whose baseline is below MIN_BASE % of the
# reader mean (default 60) are left out, as are bins without gaze position, so the same rows enter every model.
# Models: M0, random intercepts for readers and items only; M1, per-trial smooths (three basis functions each) and the
# random part of R 1, without and with an AR1 term (rho from the model without it); M2, M1 plus a te(x, y) gaze surface.
# Usage: Rscript gamm.R [bins.csv] [output folder]. Settings: NTHREADS (default 2), MIN_BASE (60), MODELS (default
# "M0,M1,M2"), RANDOM_PART ("lmm", default, as R 1; "plan": reader-by-version and item intercepts), FIG_DIR (residual
# plots of the AR1 models; default: the output folder). With an optimised BLAS (OpenBLAS) and two threads, each AR1 fit
# of the paper's data (981 trials, 175,210 bins) took 4 to 10 minutes and about 6 GB of memory.
suppressMessages(library(mgcv))
args <- commandArgs(trailingOnly = TRUE)
inp <- if (length(args) >= 1) args[1] else "bins.csv"
out <- if (length(args) >= 2) args[2] else "."
nthr <- as.integer(Sys.getenv("NTHREADS", "2"))
min_base <- as.numeric(Sys.getenv("MIN_BASE", "60"))
models <- strsplit(Sys.getenv("MODELS", "M0,M1,M2"), ",")[[1]]
random_part <- Sys.getenv("RANDOM_PART", "lmm")
dir.create(out, showWarnings = FALSE, recursive = TRUE)
sfx <- if (random_part == "plan") "_plan" else ""
sink(file.path(out, paste0("gamm_log", sfx, ".txt")), split = TRUE)

d <- read.csv(inp)
d <- d[d$baseline_pct >= min_base & is.finite(d$pupil_change) & is.finite(d$gaze_x) & is.finite(d$gaze_y), ]
d$rel <- d$pupil_change; d$x <- d$gaze_x; d$y <- d$gaze_y; d$Time <- d$time
d$Participant <- factor(d$reader); d$Item <- factor(d$item); d$Event <- factor(paste(d$reader, d$trial, sep = "_"))
d$Version <- factor(d$contrast, levels = c(0, 1))                      # 0 = reference version
d$VersionO <- as.ordered(d$Version); contrasts(d$VersionO) <- "contr.treatment"
d$IsC <- as.numeric(d$contrast == 1)                                   # for the by-reader version slope
d <- d[order(d$Event, d$Time), ]
d$start <- !duplicated(d$Event)                                        # the AR1 process restarts at each trial
term <- paste0("VersionO", levels(d$VersionO)[2]); sterm <- paste0("s(Time):", term)
cat(sprintf("rows %d, trials %d (reference %d, contrast %d), readers %d\n", nrow(d), nlevels(d$Event),
            length(unique(d$Event[d$contrast == 0])), length(unique(d$Event[d$contrast == 1])), nlevels(d$Participant)))

fixed <- "rel ~ VersionO + s(Time, k = 20) + s(Time, by = VersionO, k = 20)"
random <- if (random_part == "plan") "+ s(Time, Event, bs = 'fs', m = 1, k = 3) + s(Participant, Version, bs = 're') + s(Item, bs = 're')" else
  "+ s(Time, Event, bs = 'fs', m = 1, k = 3) + s(Participant, bs = 're') + s(Participant, IsC, bs = 're') + s(Item, bs = 're')"
cat("random part:", random_part, "\n")
fit <- function(f, rho = 0) {
  t0 <- Sys.time()
  m <- if (rho > 0) bam(as.formula(f), data = d, method = "fREML", discrete = TRUE, nthreads = nthr, rho = rho, AR.start = d$start)
       else bam(as.formula(f), data = d, method = "fREML", discrete = TRUE, nthreads = nthr)
  cat(sprintf("  fitted in %.1f min\n", as.numeric(difftime(Sys.time(), t0, units = "mins")))); m
}
lag1 <- function(r) acf(r, plot = FALSE, lag.max = 1)$acf[2]
report <- function(name, m, rho) {
  s <- summary(m, re.test = FALSE); pt <- s$p.table[term, ]; st <- s$s.table[sterm, ]
  r <- if (rho > 0) m$std.rsd else resid(m)
  cat(sprintf("%s: average difference %+.2f [%+.2f, %+.2f], p = %.3f; difference smooth edf %.2f, F = %.2f, p = %.3g; rho %.3f; lag-1 residual autocorrelation after fit %.3f\n",
              name, pt[1], pt[1] - 1.96 * pt[2], pt[1] + 1.96 * pt[2], pt[4], st[1], st[3], st[4], rho, lag1(r)))
  data.frame(model = name, est = pt[1], se = pt[2], lo = pt[1] - 1.96 * pt[2], hi = pt[1] + 1.96 * pt[2], p_avg = pt[4],
             edf_diff = st[1], F_diff = st[3], p_diff = st[4], rho = rho, resid_lag1 = lag1(r), n = nrow(d),
             n_trials = nlevels(d$Event), r2 = s$r.sq)
}
fig_dir <- Sys.getenv("FIG_DIR", out); dir.create(fig_dir, showWarnings = FALSE, recursive = TRUE)
diag_plot <- function(m, name) {                                        # residual checks of an AR1 model
  r <- m$std.rsd; png(file.path(fig_dir, paste0("gamm_residuals_", name, sfx, ".png")), width = 1800, height = 800, res = 200)
  op <- par(mfrow = c(1, 2), mar = c(4, 4, 2, 1)); acf(r, lag.max = 30, main = paste(name, "- ACF of standardised residuals"))
  qqnorm(r, main = paste(name, "- normal Q-Q plot"), pch = ".", col = "grey30"); qqline(r); par(op); dev.off()
  cat(sprintf("  %s standardised residuals: lag-1 %.3f, lag-2 %.3f, skewness %.2f, excess kurtosis %.2f\n", name,
              acf(r, plot = FALSE, lag.max = 2)$acf[2], acf(r, plot = FALSE, lag.max = 2)$acf[3],
              mean((r - mean(r))^3) / sd(r)^3, mean((r - mean(r))^4) / sd(r)^4 - 3))
}
grid <- data.frame(Time = seq(0.55, 19.95, by = 0.1))
diff_curve <- function(name, m) {                                       # population-level difference curve with CIs
  nd <- function(v) transform(grid, VersionO = factor(v, levels = levels(d$VersionO), ordered = TRUE),
                              Version = factor(v, levels = levels(d$Version)), x = mean(d$x), y = mean(d$y),
                              Event = d$Event[1], Participant = d$Participant[1], Item = d$Item[1], IsC = as.numeric(v == "1"))
  Xs <- predict(m, nd("1"), type = "lpmatrix"); Xn <- predict(m, nd("0"), type = "lpmatrix")
  keep <- !grepl("Event|Participant|Item", colnames(Xs))
  Xd <- (Xs - Xn); Xd[, !keep] <- 0
  est <- as.vector(Xd %*% coef(m)); se <- sqrt(rowSums((Xd %*% m$Vp) * Xd))
  data.frame(model = name, Time = grid$Time, diff = est, se = se, lo = est - 1.96 * se, hi = est + 1.96 * se)
}

res <- NULL; dc <- NULL
if ("M0" %in% models) {
  cat("\nM0: fixed part, random intercepts for readers and items only, no per-trial smooths, no AR1\n")
  m <- fit(paste(fixed, "+ s(Participant, bs = 're') + s(Item, bs = 're')")); res <- rbind(res, report("M0 naive", m, 0)); rm(m); invisible(gc())
}
if ("M1" %in% models) {
  cat("\nM1: per-trial smooths, no gaze term\n")
  m <- fit(paste(fixed, random)); rho1 <- lag1(resid(m)); cat(sprintf("  rho from the model without AR1: %.3f\n", rho1))
  res <- rbind(res, report("M1 without AR1", m, 0)); rm(m); invisible(gc())
  m <- fit(paste(fixed, random), rho1); res <- rbind(res, report("M1 no gaze term", m, rho1))
  dc <- rbind(dc, diff_curve("M1 no gaze term", m)); cat("\nM1 summary\n"); print(summary(m, re.test = FALSE)); diag_plot(m, "M1")
  rm(m); invisible(gc())
}
if ("M2" %in% models) {
  cat("\nM2: M1 + te(x, y) gaze surface\n")
  m <- fit(paste(fixed, random, "+ te(x, y)")); rho2 <- lag1(resid(m)); cat(sprintf("  rho from the model without AR1: %.3f\n", rho2))
  res <- rbind(res, report("M2 without AR1", m, 0)); rm(m); invisible(gc())
  m <- fit(paste(fixed, random, "+ te(x, y)"), rho2); res <- rbind(res, report("M2 gaze surface", m, rho2))
  dc <- rbind(dc, diff_curve("M2 gaze surface", m)); cat("\nM2 summary\n"); print(summary(m, re.test = FALSE)); diag_plot(m, "M2")
  rm(m); invisible(gc())
}
rownames(res) <- NULL
write.csv(res, file.path(out, paste0("gamm_summary", sfx, ".csv")), row.names = FALSE)
if (!is.null(dc)) {
  write.csv(dc, file.path(out, paste0("gamm_diff", sfx, ".csv")), row.names = FALSE)
  for (nm in unique(dc$model)) {
    z <- dc[dc$model == nm, ]
    cat(sprintf("%s curve: mean %+.2f, range %+.2f to %+.2f; pointwise 95%% CI excludes 0 at %d of %d time points\n",
                nm, mean(z$diff), min(z$diff), max(z$diff), sum(z$lo > 0 | z$hi < 0), nrow(z)))
  }
}
sink()
