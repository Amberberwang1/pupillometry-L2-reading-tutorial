# Mixed-effects model of the trial means (one row per trial)
trials <- read.csv("trials.csv")                # from run_pipeline(), 45 readers
trials <- subset(trials, baseline_pct >= 60)    # baseline: % of reader mean
# contrast: 1 = simplified, 0 = non-simplified
model <- lmer(change_0_20s ~ contrast + (1 | reader) +
                (0 + contrast | reader) + (1 | item), data = trials,
              REML = FALSE, control = lmerControl(optimizer = "bobyqa"))
confint(model, parm = "contrast", method = "Wald")   # 95% CI
