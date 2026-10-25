# R 1. Trial-level mixed-effects model of the primary measure (Section 3.7 of the tutorial).
# Reads trials.csv written by pupilread.export_for_r(): one row per trial with reader, item, contrast (1 = the version
# compared with the reference version, 0 = reference) and change_0_20s (mean pupil change from 0.5 to 20 s, as % of the
# reader mean). Trials whose baseline is below MIN_BASE % of the reader mean (default 60) are left out (Section 3.3).
# Model: crossed random intercepts for readers and items and an uncorrelated by-reader slope for version, fitted by
# maximum likelihood (lme4, bobyqa). Usage: Rscript lmm.R [trials.csv] [output.csv] [measure column]
suppressMessages(library(lme4))
args <- commandArgs(trailingOnly = TRUE)
inp <- if (length(args) >= 1) args[1] else "trials.csv"
outp <- if (length(args) >= 2) args[2] else "lmm_results.csv"
dv <- if (length(args) >= 3) args[3] else "change_0_20s"
min_base <- as.numeric(Sys.getenv("MIN_BASE", "60"))

trials <- read.csv(inp)
trials <- trials[trials$baseline_pct >= min_base & is.finite(trials[[dv]]), ]
trials$reader <- factor(trials$reader)
trials$item <- factor(trials$item)

f <- as.formula(paste(dv, "~ contrast + (1 | reader) + (0 + contrast | reader) + (1 | item)"))
m <- lmer(f, data = trials, REML = FALSE, control = lmerControl(optimizer = "bobyqa"))
b <- unname(fixef(m)["contrast"])
se <- sqrt(vcov(m)["contrast", "contrast"])
res <- data.frame(measure = dv, estimate = b, lo = b - 1.96 * se, hi = b + 1.96 * se, p = 2 * pnorm(-abs(b / se)),
                  n_trials = nrow(trials), n_readers = nlevels(droplevels(trials$reader)), singular = isSingular(m))
print(summary(m), correlation = FALSE)
print(res, digits = 3, row.names = FALSE)
write.csv(res, outp, row.names = FALSE)
