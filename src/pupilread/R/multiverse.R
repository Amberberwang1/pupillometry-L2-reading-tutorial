# The estimate under each option (Section 5 and Table 4 of the tutorial): one lme4 model per option column.
# Reads trials.csv and options.csv written by pupilread.export_for_r() from pupilread.options_table(). Each option
# column holds the trial measure under that option, missing for the trials the option leaves out; options.csv gives
# the model of each column: random part ("slope": reader intercepts, uncorrelated by-reader slope for version and item
# intercepts; "intercepts": reader and item intercepts only), covariates (already standardised) and the tested term.
# Without options.csv, every column whose name starts with "change_" or "pupil_" is fitted with the default model.
# Usage: Rscript multiverse.R [trials.csv] [options.csv] [output.csv]
suppressMessages(library(lme4))
args <- commandArgs(trailingOnly = TRUE)
inp <- if (length(args) >= 1) args[1] else "trials.csv"
opt <- if (length(args) >= 2) args[2] else "options.csv"
outp <- if (length(args) >= 3) args[3] else "multiverse_results.csv"

trials <- read.csv(inp)
trials$reader <- factor(trials$reader)
trials$item <- factor(trials$item)
spec <- if (file.exists(opt)) read.csv(opt, stringsAsFactors = FALSE, na.strings = c("NA")) else {
  cols <- grep("^(change_|pupil_)", names(trials), value = TRUE)
  data.frame(column = cols, label = cols, random = "slope", covariates = "", term = "contrast", stringsAsFactors = FALSE)
}
spec$covariates[is.na(spec$covariates)] <- ""
spec$term[is.na(spec$term) | spec$term == ""] <- "contrast"
spec$random[is.na(spec$random) | spec$random == ""] <- "slope"

fit_one <- function(r) {
  dv <- r$column
  covs <- trimws(strsplit(r$covariates, "+", fixed = TRUE)[[1]])
  covs <- covs[nzchar(covs)]
  need <- unique(c(dv, "contrast", unlist(strsplit(covs, ":", fixed = TRUE))))
  x <- trials[complete.cases(trials[, need, drop = FALSE]) & is.finite(trials[[dv]]), ]
  rand <- if (r$random == "intercepts") "+ (1 | reader) + (1 | item)" else
    "+ (1 | reader) + (0 + contrast | reader) + (1 | item)"
  f <- paste(dv, "~ contrast", if (length(covs)) paste("+", paste(covs, collapse = " + ")) else "", rand)
  m <- lmer(as.formula(f), data = x, REML = FALSE, control = lmerControl(optimizer = "bobyqa"))
  b <- unname(fixef(m)[r$term]); se <- sqrt(vcov(m)[r$term, r$term])
  data.frame(column = dv, label = r$label, term = r$term, estimate = b, lo = b - 1.96 * se, hi = b + 1.96 * se,
             p = 2 * pnorm(-abs(b / se)), n_trials = nrow(x), n_readers = nlevels(droplevels(x$reader)),
             singular = isSingular(m), formula = f)
}
res <- do.call(rbind, lapply(seq_len(nrow(spec)), function(i) {
  r <- spec[i, ]
  if (!(r$column %in% names(trials))) return(NULL)
  tryCatch(fit_one(r), error = function(e) {
    message("option ", r$column, ": ", conditionMessage(e)); NULL })
}))
write.csv(res, outp, row.names = FALSE)
print(res[, c("label", "estimate", "lo", "hi", "p", "n_trials", "singular")], digits = 3, row.names = FALSE)
