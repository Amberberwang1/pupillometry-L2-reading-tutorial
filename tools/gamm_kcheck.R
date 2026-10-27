# Basis-dimension check of the per-trial smooths (Supplementary Note S2): model M1 of gamm.R (no gaze term, AR1) with
# k = 3 (as reported) and k = 5 per trial smooth, fitted to every second reader so that the k = 5 model fits in memory.
# rho = lag-1 autocorrelation of the residuals of the k = 3 model without AR1 on the same subset.
# Reads bins.csv from pupilread.export_for_r(). Usage: Rscript gamm_kcheck.R [bins.csv] [output folder]
suppressMessages(library(mgcv))
args <- commandArgs(trailingOnly = TRUE)
inp <- if (length(args) >= 1) args[1] else "bins.csv"
out <- if (length(args) >= 2) args[2] else "."
nthr <- as.integer(Sys.getenv("NTHREADS", "2"))
min_base <- as.numeric(Sys.getenv("MIN_BASE", "60"))
dir.create(out, showWarnings = FALSE, recursive = TRUE)
sink(file.path(out, "gamm_kcheck_log.txt"), split = TRUE)
d <- read.csv(inp)
d <- d[d$baseline_pct >= min_base & is.finite(d$pupil_change) & is.finite(d$gaze_x) & is.finite(d$gaze_y), ]
ids <- sort(unique(d$reader)); keep <- ids[seq(1, length(ids), by = 2)]; d <- d[d$reader %in% keep, ]
d$rel <- d$pupil_change; d$Time <- d$time
d$Participant <- factor(d$reader); d$Item <- factor(d$item); d$Event <- factor(paste(d$reader, d$trial, sep = "_"))
d$Version <- factor(d$contrast, levels = c(0, 1)); d$VersionO <- as.ordered(d$Version); contrasts(d$VersionO) <- "contr.treatment"
d$IsC <- as.numeric(d$contrast == 1); d <- d[order(d$Event, d$Time), ]; d$start <- !duplicated(d$Event)
term <- paste0("VersionO", levels(d$VersionO)[2]); sterm <- paste0("s(Time):", term)
cat(sprintf("subset: %d readers, %d trials, %d rows\n", nlevels(d$Participant), nlevels(d$Event), nrow(d)))
fixed <- "rel ~ VersionO + s(Time, k = 20) + s(Time, by = VersionO, k = 20)"
rand <- function(k) sprintf("+ s(Time, Event, bs = 'fs', m = 1, k = %d) + s(Participant, bs = 're') + s(Participant, IsC, bs = 're') + s(Item, bs = 're')", k)
fit <- function(k, rho = 0) {
  t0 <- Sys.time(); f <- as.formula(paste(fixed, rand(k)))
  m <- if (rho > 0) bam(f, data = d, method = "fREML", discrete = TRUE, nthreads = nthr, rho = rho, AR.start = d$start)
       else bam(f, data = d, method = "fREML", discrete = TRUE, nthreads = nthr)
  cat(sprintf("  k = %d, rho = %.3f: fitted in %.1f min\n", k, rho, as.numeric(difftime(Sys.time(), t0, units = "mins")))); m
}
rep_ <- function(name, m) {
  s <- summary(m, re.test = FALSE); pt <- s$p.table[term, ]; st <- s$s.table[sterm, ]
  cat(sprintf("%s: average difference %+.2f [%+.2f, %+.2f], p = %.3f; difference smooth edf %.2f, F = %.2f, p = %.3g\n",
              name, pt[1], pt[1] - 1.96 * pt[2], pt[1] + 1.96 * pt[2], pt[4], st[1], st[3], st[4]))
  data.frame(model = name, est = pt[1], lo = pt[1] - 1.96 * pt[2], hi = pt[1] + 1.96 * pt[2], p = pt[4], edf = st[1], F = st[3],
             p_smooth = st[4], n_readers = nlevels(d$Participant), n_trials = nlevels(d$Event))
}
m <- fit(3); rho <- acf(resid(m), plot = FALSE, lag.max = 1)$acf[2]; cat(sprintf("rho (k = 3, no AR1): %.3f\n", rho)); rm(m); invisible(gc())
m <- fit(3, rho); r3 <- rep_("k = 3, AR1", m); rm(m); invisible(gc())
m <- fit(5, rho); r5 <- rep_("k = 5, AR1", m); rm(m); invisible(gc())
write.csv(rbind(r3, r5), file.path(out, "gamm_kcheck.csv"), row.names = FALSE)
sink()
