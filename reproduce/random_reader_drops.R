# Random reader drops for the note of Table S2: the primary estimate refitted after dropping k readers at random,
# to compare with the row that drops the four readers recorded in the tracker's ellipse-fitting pupil mode.
# Same model as lmm.R and multiverse.R (random intercepts for readers and items, a by-reader slope for version).
#
# Usage: Rscript random_reader_drops.R trials.csv out.csv [draws = 2000] [k = 4] [seed = 2026]
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("usage: Rscript random_reader_drops.R trials.csv out.csv [draws] [k] [seed]")
suppressMessages(library(lme4))
draws <- if (length(args) > 2) as.integer(args[3]) else 2000L
k <- if (length(args) > 3) as.integer(args[4]) else 4L
seed <- if (length(args) > 4) as.integer(args[5]) else 2026L

d <- read.csv(args[1], colClasses = c(reader = "character", item = "character"))
d <- d[!is.na(d$change_0_20s), ]
readers <- sort(unique(d$reader))
ctrl <- lmerControl(optimizer = "bobyqa", calc.derivs = FALSE)
estimate <- function(x) {
  m <- lmer(change_0_20s ~ contrast + (1 | reader) + (0 + contrast | reader) + (1 | item), data = x,
            REML = FALSE, control = ctrl)
  unname(fixef(m)["contrast"])
}

set.seed(seed)
out <- data.frame(draw = seq_len(draws), dropped = NA_character_, n_trials = NA_integer_, estimate = NA_real_)
for (i in seq_len(draws)) {
  drop <- sort(sample(readers, k))
  x <- d[!(d$reader %in% drop), ]
  out$dropped[i] <- paste(drop, collapse = " ")
  out$n_trials[i] <- nrow(x)
  out$estimate[i] <- estimate(x)
}
write.csv(out, args[2], row.names = FALSE)
cat(sprintf("%d draws of %d of %d readers (seed %d): estimate median %.3f, 2.5%% %.3f, 97.5%% %.3f\n", draws, k,
            length(readers), seed, median(out$estimate), quantile(out$estimate, 0.025), quantile(out$estimate, 0.975)))
