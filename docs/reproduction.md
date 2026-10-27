# Reproducing the paper with pupilread

With its defaults, pupilread reproduces 36 of the 36 model estimates of Tables 3 and S2 (to the printed digits, with the printed trial counts) and 84 of the 84 numbers quoted in the text and supplement. With `prepare --legacy`, it reproduces the first full-study draft, which the original scripts computed: 32 of 32 estimates and 66 of 66 numbers, and every trial value and bin (last section).

Run on the 45 readers' Data Viewer reports (not included: participant data):

```
python tools/reproduce_paper.py prepare --data "Full study results" --cache cache          # stage 1
python tools/reproduce_paper.py analyse --cache cache --out reproduction --gamm --kcheck  # stage 2, needs R
python tools/reproduce_paper.py prepare --data "Full study results" --cache cache_legacy --legacy
python tools/reproduce_paper.py analyse --cache cache_legacy --out reproduction_legacy --gamm --old "<old outputs>"
python tools/reproduction_report.py reproduction reproduction_legacy docs/reproduction.md
```

## What changed between the draft and the paper

The original scripts made three assumptions that pupilread corrects (`CHANGELOG.md`): durations counted in samples assumed 1,000 Hz, although 6 of the 45 recordings were made at 2,000 Hz; blink padding summed blink flags in 8-bit integers, which overflow where blinks fill more than 127 of the 201 samples around a sample, so short gaps between blinks stayed valid; and one reader's reports listed every row twice. The repeated rows also doubled that reader's word counts in the companion study's screen for skimmed texts, so five of the reader's trials crossed its reading-rate ceiling; `reproduce_paper.py` recomputes the screen for that reader without the repeats (61 trials excluded as skimmed or incomplete, against 66). The paper reports the corrected values.

## Tables 3 and S2

| Table | Option | Paper (pupilread defaults) | Status | Draft (original scripts) | Legacy mode | Trials (paper, draft) |
| --- | --- | --- | --- | --- | --- | --- |
| 3 | change_0_20s | 1.37 [−0.20, 2.94], p = .087 | match | 1.27 [−0.28, 2.83], p = .108 | match | 986, 982 |
| 3 | fixations | 1.38 [−0.31, 3.07], p = .110 | match | 1.32 [−0.36, 3.00], p = .124 | match | 924, 919 |
| 3 | valid_75 | 1.58 [0.00, 3.16], p = .049 | match | 1.53 [−0.03, 3.10], p = .054 | match | 930, 927 |
| 3 | baseline_0_500 | 1.51 [0.12, 2.90], p = .033 | match | 1.45 [0.06, 2.83], p = .041 | match | 986, 982 |
| 3 | low_baselines_kept | 1.13 [−0.48, 2.74], p = .168 | match | 1.03 [−0.56, 2.62], p = .204 | match | 988, 984 |
| 3 | no_baseline | 1.36 [0.48, 2.25], p = .003 | match | 1.39 [0.51, 2.28], p = .002 | match | 986, 982 |
| 3 | baseline_covariate | 1.36 [0.51, 2.20], p = .002 | match | 1.36 [0.51, 2.20], p = .002 | match | 986, 982 |
| 3 | diameter | 0.71 [−0.04, 1.47], p = .063 | match | 0.67 [−0.07, 1.42], p = .078 | match | 986, 982 |
| 3 | whole_trial | 1.67 [0.11, 3.23], p = .036 | match | 1.58 [0.04, 3.12], p = .045 | match | 986, 982 |
| 3 | random_intercepts | 1.35 [−0.07, 2.78], p = .062 | match | 1.26 [−0.16, 2.68], p = .082 | match | 986, 982 |
| 3 | control_predictors | 0.89 [−0.67, 2.44], p = .263 | match | 0.81 [−0.73, 2.34], p = .303 | match | 986, 982 |
| 3 | gaze_regression | 1.26 [−0.48, 2.99], p = .155 | match | 1.16 [−0.55, 2.87], p = .184 | match | 986, 982 |
| 3 | gaze_steps_eye | 1.85 [0.06, 3.63], p = .042 | match | 1.75 [−0.03, 3.52], p = .054 | match | 986, 982 |
| 3 | gaze_steps_type | 0.63 [−0.94, 2.19], p = .434 | match | 0.54 [−1.02, 2.09], p = .499 | match | 986, 982 |
| 3 | gaze_geometric | 0.85 [−0.71, 2.42], p = .284 | match | not in the draft |  | 986, – |
| 3 | GAMM M0 naive | 1.29 [1.16, 1.42], p < .001 | match | 1.22 [1.09, 1.35] | match | 986, 982 |
| 3 | GAMM M1 no gaze term | 1.33 [−0.22, 2.87], p = .092 | match | 1.23 [−0.29, 2.76], p = .113 | match | 986, 982 |
| 3 | GAMM M2 gaze surface | 1.96 [0.40, 3.52], p = .014 | match | 2.04 [0.51, 3.58], p = .009 | match | 986, 982 |
| S2 | fixations_same_trials | 1.45 [−0.22, 3.11], p = .088 | match | 1.38 [−0.27, 3.03], p = .101 | match | 924, 919 |
| S2 | interpolated | 1.37 [−0.20, 2.94], p = .087 | match | 1.27 [−0.28, 2.83], p = .108 | match | 986, 982 |
| S2 | window_2_20 | 1.49 [−0.12, 3.10], p = .069 | match | 1.40 [−0.19, 2.99], p = .084 | match | 986, 982 |
| S2 | window_3_20 | 1.55 [−0.06, 3.17], p = .060 | match | 1.47 [−0.13, 3.08], p = .072 | match | 986, 982 |
| S2 | window_5_20 | 1.47 [−0.15, 3.10], p = .076 | match | 1.40 [−0.22, 3.02], p = .090 | match | 986, 982 |
| S2 | left_eye | 1.41 [−0.88, 3.70], p = .228 | match | 1.41 [−0.88, 3.70], p = .228 | match | 477, 477 |
| S2 | right_eye | 1.43 [−0.67, 3.53], p = .183 | match | 1.27 [−0.80, 3.34], p = .228 | match | 509, 505 |
| S2 | whole_trial_covariates | 1.66 [0.08, 3.23], p = .039 | match | 1.57 [0.02, 3.13], p = .047 | match | 986, 982 |
| S2 | cut_1s | 1.37 [−0.20, 2.94], p = .087 | match | 1.28 [−0.28, 2.83], p = .107 | match | 986, 982 |
| S2 | cut_2s | 1.37 [−0.20, 2.93], p = .087 | match | 1.27 [−0.28, 2.82], p = .108 | match | 986, 982 |
| S2 | gaze_regression_time | 1.23 [−0.47, 2.94], p = .156 | match | 1.14 [−0.55, 2.83], p = .185 | match | 986, 982 |
| S2 | gaze_steps_reader | 0.91 [−1.19, 3.00], p = .396 | match | 0.80 [−1.28, 2.89], p = .450 | match | 986, 982 |
| S2 | gaze_steps_map | 0.93 [−0.69, 2.56], p = .261 | match | 0.84 [−0.78, 2.45], p = .310 | match | 986, 982 |
| S2 | gaze_hybrid | 1.46 [−0.13, 3.05], p = .072 | match | not in the draft |  | 986, – |
| S2 | control_predictors_cos_theta | 0.98 [−0.57, 2.54], p = .214 | match | not in the draft |  | 986, – |
| S2 | GAMM M1 without AR1 | 1.34 [−0.26, 2.94], p = .100 | match | 1.24 [−0.33, 2.82], p = .122 | match | 986, 982 |
| S2 | GAMM M2 without AR1 | 0.85 [−0.56, 2.26], p = .237 | match | 0.79 [−0.77, 2.36], p = .320 | match | 986, 982 |
| S2 | centroid_only | 1.09 [−0.57, 2.75], p = .198 | match | not in the draft |  | 893, – |

The rows gaze_geometric, gaze_hybrid and control_predictors_cos_theta use the layout of eye, camera and screen in `STUDY_LAYOUT` of `tools/reproduce_paper.py` (`analyse --layout` replaces it); `geometric_check.csv` compares the artifact this layout predicts with the measured saccade steps (Section 3.4), and `geometric_scale.csv` holds the scale factors of gaze_hybrid.

## Numbers in the text

| Number | Paper | pupilread | Status | Draft | Legacy mode |
| --- | --- | --- | --- | --- | --- |
| 3.1 fixation pupil vs samples, r (> .9999) | 0.9999 | 0.999994 | match | 0.9999 | match |
| 3.1 retained fixations cover reading time (%) | 73 | 73.16 | match | 73 | match |
| 3.2 samples lost (%) | 10.1 | 10.148 | match | 9.9 | match |
| 3.2 invalid (%) | 4.1 | 4.102 | match | 4.1 | match |
| 3.2 lost to blink padding (%) | 6.0 | 6.046 | match | 5.8 | match |
| 3.2 trials with < 50% valid samples | 12 | 12.0 | match | 12 | match |
| 3.2 of them non-simplified | 5 | 5.0 | match | 5 | match |
| 3.2 of them simplified | 7 | 7.0 | match | 7 | match |
| 3.3 trials without a 0-200 ms baseline | 19 | 19.0 | match | 18 | match |
| 3.3 trials without a 0-500 ms baseline | 9 | 9.0 | match | 8 | match |
| 3.3 low baselines (< 60%) | 2 | 2.0 | match | 2 | match |
| 3.3 low baselines that were non-simplified | 2 | 2.0 | match | 2 | match |
| 3.3 analysed trials | 986 | 986.0 | match | 982 | match |
| 3.3 baseline difference, 0-200 ms (%) | -0.14 | -0.1394 | match | -0.11 | match |
| 3.3 baseline difference, 0-500 ms (%) | -0.19 | -0.1927 | match | -0.18 | match |
| 3.3 onset: time of the first rise (ms, about) | 200 | 250.0 | match | 200 | match |
| 3.3 onset: time of the minimum (ms, about) | 700 | 750.0 | match | 700 | match |
| 3.3 onset: second peak (s, 1.5-2) | 1.5-2.0 | 1.85 | match | 1.5-2.0 | match |
| 3.4 gaze shift, simplified minus non-simplified, x (px, about -80) | -80 | -81.76 | match | -80 | match |
| 3.4 gaze shift, simplified minus non-simplified, y (px, about 40) | 40 | 39.97 | match | 40 | match |
| 3.4 return-sweep step, left eye (%) | 6.5 | 6.544 | match | 6.5 | match |
| 3.4 return-sweep step, right eye (%) | 2.9 | 2.921 | match | 2.9 | match |
| 3.5 trial duration, non-simplified (s) | 43.2 | 43.187 | match | 43.2 | match |
| 3.5 trial duration, simplified (s) | 38.5 | 38.457 | match | 38.5 | match |
| 3.5 trials ending before 20 s | 77 | 77.0 | match | 76 | match |
| 3.5 of them simplified | 46 | 46.0 | match | 45 | match |
| 3.5 rise in the last second before the key press (%) | 5.1 | 5.054 | match | 5.0 | match |
| 3.5 rise, non-simplified minus simplified, p | 0.005 | 0.00466 | match | 0.005 | match |
| 3.5 blink response: largest rise, mean of versions (%) | about 3.5 | 3.486 | match | about 3.0 | match |
| 3.5 blink response: lowest point, mean of versions (%) | about -3.5 | -3.543 | match | about -3.0 | match |
| 3.5 blink rate, non-simplified (per s) | 0.32 | 0.3162 | match | 0.32 | match |
| 3.5 blink rate, simplified (per s) | 0.32 | 0.3244 | match | 0.33 | match |
| 3.5 saccade rate, non-simplified (per s) | 3.51 | 3.5054 | match | 3.51 | match |
| 3.5 saccade rate, simplified (per s) | 3.52 | 3.5168 | match | 3.52 | match |
| 3.6 trials excluded as skimmed or incomplete | 61 | 61.0 | match | 66 | match |
| 3.6 trials read | 1080 | 1080.0 | match | 1080 | match |
| 3.6 grand mean: median difference from 3 s (percentage points) | 1.6 | 1.563 | match | 1.5 | match |
| 3.7 fixations from 0.5 to 20 s | 54227 | 54227.0 | match | 54033 | match |
| 3.7 fixation-level t | 11.6 | 11.5972 | match | 11.06 | match |
| 3.7 paired t-test on reader means, p | 0.08 | 0.0797 | match | 0.088 | match |
| 3.7 control predictors, no adjustment on the same bins (%) | 1.35 | 1.3482 | match | 1.25 | match |
| 3.7 control predictors, all (%) | 0.89 | 0.8879 | match | 0.81 | match |
| 3.7 text density changed the estimate by (percentage points) | 0.05 | 0.052 | match | 0.06 | match |
| 3.7 GAMM rho (AR1) | 0.92 | 0.9217 | match | 0.92 | match |
| 3.7 GAMM M0 residual lag-1 | 0.98 | 0.9779 | match | 0.98 | match |
| 3.7 GAMM M1 AR1 residual lag-1 | 0.27 | 0.2709 | match | about 0.23 | match |
| 4.4 d_z across readers | 0.267 | 0.26742 | match | 0.26 | match |
| 4.4 readers for 80% power | 113 | 113.0 | match | 118 | match |
| 4.4 readers for 80% power at d_z = 0.3 | 90 | 90.0 | match | 89 | match |
| S1 detector flags inside padded blinks, median (%) | 92.8 | 92.754 | match | 91.9 | match |
| S1 detector flags outside padded blinks, median (%) | 2.3 | 2.317 | match | 2.1 | match |
| S1 trials kept after the exclusions for skimming and missing data | 1007 | 1007.0 | match | 1002 | match |
| S2 rho without gaze surface | 0.922 | 0.92174 | match | 0.917 | match |
| S2 rho with gaze surface | 0.92 | 0.92037 | match | 0.918 | match |
| S2 excess kurtosis without gaze surface | 53 | 53.27 | match | 58 | match |
| S2 excess kurtosis with gaze surface | 29 | 28.72 | match | 28 | match |
| S2 k-check readers | 23 | 23.0 | match | 23 | match |
| S2 k-check trials | 487 | 487.0 | match | 488 | match |
| S2 k-check, k = 3: estimate (%) | 2.31 | 2.3116 | match | 2.27 | match |
| S2 k-check, k = 3: lower (%) | 0.3 | 0.2964 | match | 0.26 | match |
| S2 k-check, k = 3: upper (%) | 4.33 | 4.3268 | match | 4.28 | match |
| S2 k-check, k = 5: estimate (%) | 2.29 | 2.2918 | match | 2.25 | match |
| S2 k-check, k = 5: lower (%) | 0.27 | 0.2688 | match | 0.23 | match |
| S2 k-check, k = 5: upper (%) | 4.31 | 4.3148 | match | 4.27 | match |
| 5 smallest estimate in Table 3 (%) | 0.63 | 0.6257 | match | 0.54 | match |
| 5 largest estimate in Table 3 (%) | 1.96 | 1.9619 | match | 2.04 | match |
| 3.3 baseline difference, 0-200 ms: lower (%) | -1.99 | -1.9911 | match |  |  |
| 3.3 baseline difference, 0-200 ms: upper (%) | 1.71 | 1.7123 | match |  |  |
| 3.3 baseline difference, 0-500 ms: lower (%) | -1.77 | -1.767 | match |  |  |
| 3.3 baseline difference, 0-500 ms: upper (%) | 1.38 | 1.3815 | match |  |  |
| 3.6 trials with residual downward spikes (%) | 26 | 25.96 | match |  |  |
| 3.6 valid reading time per residual spike (s, about 80) | about 80 | 78.561 | match |  |  |
| 3.6 residual spikes removed: estimate (%) | 1.36 | 1.3551 | match |  |  |
| 3.6 residual spikes removed: p | 0.092 | 0.09202 | match |  |  |
| Table S2 note: random four-reader drops with an estimate this low (%) | 12.6 | 12.6 | match |  |  |
| Table S2 note: random draws | 2000 | 2000.0 | match |  |  |
| 3.4 geometric model: horizontal artifact, left eye (pp per 100 px) | 0.15 | 0.1548 | match |  |  |
| 3.4 geometric model: horizontal artifact, right eye (pp per 100 px) | -0.01 | -0.0113 | match |  |  |
| 3.4 saccade steps: horizontal artifact, left eye (pp per 100 px) | -1.41 | -1.4144 | match |  |  |
| 3.4 saccade steps: horizontal artifact, right eye (pp per 100 px) | -0.57 | -0.5671 | match |  |  |
| 3.4 geometric model: return-sweep step, left eye (%) | -0.8 | -0.837 | match |  |  |
| 3.4 geometric model: return-sweep step, right eye (%) | 0.0 | 0.046 | match |  |  |
| S2 geometric model scaled to the saccade steps: scale factor, left eye | -0.81 | -0.8129 | match |  |  |
| S2 geometric model scaled to the saccade steps: scale factor, right eye | 0.6 | 0.5957 | match |  |  |

## Legacy mode against the outputs of the original scripts

Largest absolute difference between the package in legacy mode and the files the original scripts wrote (trial values in % of the reader mean, bins in arbitrary units or pixels):

| Quantity | Compared | Missing in one | Largest difference |
| --- | --- | --- | --- |
| trial: change_0_20s vs 03b change_0_20s | 982 | 0 | 4.3e-14 |
| trial: whole_trial vs 03b change_whole_trial | 982 | 0 | 5e-14 |
| trial: interpolated vs 03b change_0_20s_interpolated | 982 | 0 | 5.5e-14 |
| trial: baseline_0_500 vs 03b change_0_20s_baseline_500 | 982 | 0 | 5.3e-14 |
| trial: gaze_regression vs 03b change_0_20s_gaze_regression | 982 | 0 | 6e-14 |
| trial: gaze_regression_time vs 03b change_0_20s_gaze_regression_time | 982 | 0 | 5.3e-14 |
| trial: no_baseline vs 03b pupil_0_20s_uncorrected | 982 | 0 | 2.1e-14 |
| trial: diameter vs 03b change_0_20s_diameter | 982 | 0 | 4.1e-14 |
| trial: baseline_denominator vs 03b change_0_20s_baseline_denominator | 982 | 0 | 3.9e-14 |
| trial: fixations vs 03b change_0_20s_fixations | 919 | 0 | 0 |
| trial: baseline_pct vs 03b baseline_pct | 984 | 0 | 4.3e-14 |
| trial: duration_s vs 03b duration_s | 984 | 0 | 0 |
| trial: blink_rate vs 03b blink_rate | 984 | 0 | 2.2e-16 |
| trial: saccade_rate vs 03b saccade_rate | 984 | 0 | 8.9e-16 |
| trial: pct_valid vs 03b pct_valid | 984 | 0 | 1.4e-14 |
| trial: low_baselines_kept vs 03b change_0_20s | 984 | 0 | 4.3e-14 |
| trial: window_2_20 vs L w2_20 | 982 | 0 | 4.3e-14 |
| trial: window_3_20 vs L w3_20 | 982 | 0 | 4.3e-14 |
| trial: window_5_20 vs L w5_20 | 982 | 0 | 3.9e-14 |
| trial: cut_1s vs L m20_cut1 | 982 | 0 | 4.1e-14 |
| trial: cut_2s vs L m20_cut2 | 982 | 0 | 4.1e-14 |
| trial: gaze_steps_eye vs L4_trials m20_step_eye | 982 | 0 | 5.7e-14 |
| trial: gaze_steps_reader vs L4_trials m20_step_reader | 982 | 0 | 6.6e-14 |
| trial: gaze_steps_type vs L4E_trials m20_E1 | 982 | 0 | 6.2e-14 |
| trial: gaze_steps_map vs L4E_trials m20_E2 | 982 | 0 | 6e-14 |
| trial: controls_K0 vs K adj_K0 | 982 | 0 | 4.3e-14 |
| trial: controls_K1 vs K adj_K1 | 982 | 0 | 5e-14 |
| trial: controls_K2 vs K adj_K2 | 982 | 0 | 4.1e-14 |
| trial: controls_K3 vs K adj_K3 | 982 | 0 | 4.3e-14 |
| trial: controls_K4 vs K adj_K4 | 982 | 0 | 9.9e-14 |
| 20 ms bins: pupil vs per_reader p_rm | 1865916 | 0 | 0 |
| 20 ms bins: pupil_interp vs per_reader p_ip | 2048804 | 0 | 0 |
| 20 ms bins: n_valid vs per_reader nvalid | 2071087 | 0 | 0 |
| 20 ms bins: gaze_x vs per_reader x | 1865338 | 0 | 0 |
| 20 ms bins: gaze_y vs per_reader y | 1865338 | 0 | 0 |
| 20 ms bins of kept trials: new bins without an old bin | 2071087 | 0 |  |
| trial data loss: pct_valid vs per_reader pct_valid | 1079 | 0 | 0 |
| trial data loss: pct_invalid vs per_reader pct_invalid | 1079 | 0 | 0 |
| trial data loss: pct_blink_pad vs per_reader pct_blinkpad_loss | 1079 | 0 | 0 |
| trial data loss: duration_s vs per_reader dur_s | 1079 | 0 | 0 |
| trial data loss: n_blinks vs per_reader blink_n | 1079 | 0 | 0 |
| trial data loss: n_saccades vs per_reader sacc_n | 1079 | 0 | 0 |
| saccades with a step: new vs old | 98723 | 98723 |  |
| saccades: step vs L4 step | 98723 | 0 | 0 |
| saccades: late vs L4 late | 91791 | 0 | 2.8e-14 |
| saccades: dx vs L4 dx | 98729 | 0 | 0 |
| saccades: dy vs L4 dy | 98729 | 0 | 0 |
| saccades: landing vs L4 L | 98729 | 0 | 0 |
| 100 ms bins: rows only in one | 175961 | 0 |  |
| 100 ms bins: pupil_change vs H rel | 175961 | 0 | 5e-14 |
| 100 ms bins: gaze_x vs H x | 175846 | 0 | 2.3e-13 |
| 100 ms bins: gaze_y vs H y | 175846 | 0 | 2.3e-13 |

## Software

Stage 2: Python 3.13.16, pupilread 1.0.0, numpy 2.5.4, pandas 3.1.0, scipy 1.18.1, matplotlib 3.11.2. R version 4.3.3 (2024-02-29) ; lme4 1.1.35.1 ; mgcv 1.9.1 ; BLAS /usr/lib/x86_64-linux-gnu/openblas-pthread/libblas.so.3.

Stage 1: Linux aarch64 (the Linux virtual machine of the computer that holds the recordings), Python 3.10.12, pupilread 1.0.0 (installed wheel), numpy 2.2.6, pandas 2.3.3, scipy 1.15.3.
