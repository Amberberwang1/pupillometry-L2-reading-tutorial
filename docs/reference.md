# pupilread 1.0.0: function reference

Generated from the docstrings by `tools/make_reference.py`. Defaults are the paper's primary choices.

## 3.1 Reading data and data level

### `read_eyelink(path: 'PathLike', messages: 'Optional[Union[PathLike, pd.DataFrame]]' = None, onset: 'str' = 'DISPLAY_target', end: 'str' = 'KEYBOARD_endTarget', eye: 'str' = 'auto', reader: 'Optional[str]' = None, design=None, pupil_unit: 'str' = 'area', encoding: 'str' = 'utf-8-sig', chunksize: 'Optional[int]' = 500000, drop_duplicates: 'bool' = True) -> 'pd.DataFrame'`

```
Read an EyeLink Data Viewer sample report into the sample table (stage 3.1).

Parameters
----------
path : str or path
    Sample report exported from Data Viewer (tab-separated, '.' for missing values). Only the columns needed are
    read: TRIAL_INDEX, TIMESTAMP, TRIAL_START_TIME, EYE_TRACKED and, for each eye, PUPIL_SIZE, GAZE_X, GAZE_Y,
    IN_BLINK and IN_SACCADE (for example ``RIGHT_PUPIL_SIZE``).
messages : str, path or DataFrame, optional
    Message report (or the table from :func:`read_messages`) giving the text onset and the end-of-reading key press
    of each trial. Without it, a ``SAMPLE_MESSAGE`` column is used if the report has one, otherwise the whole trial.
onset, end : str
    Message texts that mark text onset and the end-of-reading key press (our study: ``DISPLAY_target`` and
    ``KEYBOARD_endTarget``).
eye : {"auto", "left", "right"}
    Eye to read. ``"auto"`` takes the eye named in EYE_TRACKED in most samples, or else the eye with more pupil data.
reader : str, optional
    Reader identifier; defaults to the report's RECORDING_SESSION_LABEL (the EDF session name), else the file name.
design : DataFrame, dict or CSV path, optional
    Table with columns trial (TRIAL_INDEX) and/or item, version and optionally reader; trials missing from it (such as
    practice texts) are dropped. Without a design, item = trial and version is missing.
pupil_unit : {"area", "diameter"}
    Unit set in the EyeLink recording; stored in ``attrs['pupil_unit']`` (see :func:`to_diameter`).
chunksize : int or None
    Rows read at a time; samples outside the text-onset-to-key-press window are dropped chunk by chunk, so that
    reports of several gigabytes fit in memory. None reads the file at once.
drop_duplicates : bool
    Drop rows that repeat the trial and time stamp of an earlier row (some exports contain every sample twice),
    with a warning. Duplicated rows would otherwise shorten blink padding and other durations counted in samples.

Returns
-------
DataFrame
    The sample table: one row per sample from text onset to the key press, ``time`` in ms from text onset.
```

### `read_csv(path: 'PathLike', columns: 'Mapping[str, str]', hz: 'Optional[float]' = None, missing=0, sep: 'str' = ',', reader: 'Optional[str]' = None, design=None, onset=None, pupil_unit: 'str' = 'diameter', blink_codes: 'Optional[Callable]' = None) -> 'pd.DataFrame'`

```
Read any sample-level file with a column mapping (in the spirit of gazeR's ``make_gazer()``).

Parameters
----------
path : str or path
    A delimited text file with one row per sample.
columns : dict
    Maps our column names to the file's: ``time`` and ``pupil`` are required; ``reader``, ``trial`` (or ``item``),
    ``version``, ``eye``, ``gaze_x``, ``gaze_y``, ``in_blink``, ``in_saccade`` and ``trial_end`` are optional. A
    missing ``trial_end`` is set to the last sample of the trial.
hz : float, optional
    Sampling rate; estimated from the time stamps if omitted.
missing : number or list
    Value(s) that code missing pupil size, set to NaN (for example 0 or -1).
onset : str or float, optional
    If ``time`` is not yet relative to text onset, a column giving the onset time of each trial (same unit) or a
    constant to subtract.
pupil_unit : {"area", "diameter"}
    Unit of the pupil column, stored in ``attrs['pupil_unit']``.
blink_codes : callable, optional
    Function mapping the raw ``in_blink`` column to booleans (default: values >= 1 or True).

Returns
-------
DataFrame
    The sample table, sorted by reader, trial and time.
```

### `read_fixations(path: 'PathLike', messages: 'Optional[Union[PathLike, pd.DataFrame]]' = None, onset: 'str' = 'DISPLAY_target', end: 'str' = 'KEYBOARD_endTarget', reader: 'Optional[str]' = None, design=None, encoding: 'str' = 'utf-8-sig') -> 'pd.DataFrame'`

```
Read an EyeLink Data Viewer fixation report into a fixation table, times in ms from text onset.

Columns: reader, item, trial, version, start, end, duration, x, y, pupil, blink_around (NONE, BEFORE, AFTER or
BOTH) and ia (interest area, if exported). Duplicate rows are dropped. Use the same ``messages`` and ``design`` as
for :func:`read_eyelink` so that fixations and samples share the time origin.
```

### `read_messages(path: 'PathLike', encoding: 'str' = 'utf-8-sig') -> 'pd.DataFrame'`

```
Read a Data Viewer message report into columns trial, text and time (ms from trial start).
```

### `read_design(design) -> 'Optional[pd.DataFrame]'`

```
Return a design table (columns reader?, trial and/or item, version) from a DataFrame, dict or CSV path.

A dict maps trial (or item) numbers to version labels and applies to every reader.
```

### `trial_windows(messages: 'pd.DataFrame', onset: 'str' = 'DISPLAY_target', end: 'str' = 'KEYBOARD_endTarget') -> 'pd.DataFrame'`

```
Text onset and end-of-reading times per trial (ms from trial start), from a message table.

The first occurrence of each message in a trial is used. Trials without both messages are left out.
```

### `to_diameter(data: 'pd.DataFrame', column: 'str' = 'pupil') -> 'pd.DataFrame'`

```
Square root of pupil area, for analyses on the diameter scale (Section 3.3).

Applied to bins (as in the paper, the square root of each 20 ms bin mean) or to samples. Columns ``pupil``,
``pupil_interp`` and ``pupil_corrected`` are transformed if present; ``attrs['pupil_unit']`` becomes "diameter".
```

### `bin(samples: 'pd.DataFrame', bin_ms: 'float' = 20, min_valid: 'float' = 0.5) -> 'pd.DataFrame'`

```
Average samples in time bins (stage 3.1; paper: 20 ms bins, at least half of their samples valid).

Pupil size is averaged over valid samples (missing ones are skipped), as are gaze coordinates; an interpolated trace
(``pupil_interp``) and a gaze-corrected trace are averaged over all their finite values. Bins keep their sample
counts, so that reader means can weight them; ``ok`` marks bins with at least ``min_valid`` of their samples valid,
and later stages use only those.

Returns
-------
DataFrame
    One row per trial and bin: reader, item, trial, version, eye, time (bin start, ms from text onset), pupil,
    n_valid, n_samples, ok, gaze_x, gaze_y, pupil_interp (if present), trial_end and duration (ms from the first to
    the last sample of the trial). ``attrs`` record bin_ms, hz, min_valid and samples_per_bin.
```

### `compare_levels(samples: 'pd.DataFrame', fixations: 'pd.DataFrame', min_fix_ms: 'float' = 80) -> 'Levels'`

```
Compare the pupil value of each fixation with the mean of the valid samples inside it (stage 3.1).

Parameters
----------
samples : DataFrame
    Samples after :func:`pad_blinks` (one or more readers).
fixations : DataFrame
    Fixation table (:func:`read_fixations`); retained fixations are those of at least ``min_fix_ms`` that do not
    border a blink.

Returns
-------
Levels
    ``fixations``: one row per retained fixation with pupil (fixation report), pupil_samples (mean of the valid
    samples from fixation start to end) and n_valid. ``summary``: correlation r and mean absolute difference over
    fixations with both values, and coverage (retained fixation time / reading time, mean over trials).
```

### `retained_fixations(fixations: 'pd.DataFrame', min_fix_ms: 'float' = 80, exclude_blinks: 'bool' = True) -> 'pd.DataFrame'`

```
Fixations of at least ``min_fix_ms`` that do not border a blink (the fixations retained in the paper).
```

### `fixation_means(fixations: 'pd.DataFrame', reader_means: 'pd.Series', window: 'Tuple[float, Optional[float]]' = (500, 20000), baseline: 'Tuple[float, float]' = (0, 200), min_fix_ms: 'float' = 80, name: 'str' = 'change_fixations') -> 'pd.DataFrame'`

```
Trial means from fixation averages instead of samples (the fixation-level option of Table 3).

The baseline is the mean pupil value of retained fixations that overlap the baseline window, the trial value the
mean of retained fixations that start within ``window``; the change is expressed as % of the reader mean, as for
samples.
```

## 3.2 Blinks and artifacts

### `pad_blinks(samples: 'pd.DataFrame', pad_ms: 'float' = 100, pupil_range: 'Tuple[float, float]' = (100, 10000)) -> 'pd.DataFrame'`

```
Pad every blink and set padded and invalid samples to missing (stage 3.2; Python 2 of the paper).

Parameters
----------
samples : DataFrame
    Sample table (:func:`read_eyelink`, :func:`read_csv`).
pad_ms : float
    Padding on each side of every blink, in ms (paper: 100 ms; 50 to 100 ms are common).
pupil_range : (low, high)
    Pupil values outside this range, like missing values, count as invalid (paper: 100 to 10,000 area units).

Returns
-------
DataFrame
    The samples with ``pupil`` set to NaN where invalid or within a padded blink, and new columns ``pupil_raw``
    (as recorded), ``invalid``, ``blink_pad`` (padded blink, blink included) and ``valid``.
```

### `detect_blinks(samples: 'pd.DataFrame', method: 'str' = 'speed', mad_k: 'float' = 16, pad_ms: 'float' = 50, smooth_ms: 'float' = 10, pupil_range: 'Tuple[float, float]' = (100, 10000), column: 'str' = 'in_blink') -> 'pd.DataFrame'`

```
Flag blinks and artifacts from the pupil signal, for trackers without blink events (Kret & Sjak-Shie, 2019).

Samples count as artifacts if pupil size is missing or outside ``pupil_range``, or if dilation speed exceeds the
trial's median speed plus ``mad_k`` median absolute deviations; speed outliers are widened by ``pad_ms``. Speed is
computed on ``smooth_ms`` means, because at 1,000 Hz the quantised pupil signal makes the median speed zero.

Parameters
----------
method : {"speed"}
    Detection method (only the dilation-speed filter is implemented).
column : str
    Column that receives the flags. The default overwrites ``in_blink``, so that :func:`pad_blinks` pads the
    detected stretches; use another name (e.g. ``"blink_speed"``) to compare with tracker blinks.

Returns
-------
DataFrame
    The samples with the boolean ``column`` (invalid or speed outlier), ``speed_outlier`` (the widened speed
    outliers alone) and the trial's speed threshold in ``speed_threshold``.
```

### `detector_agreement(samples: 'pd.DataFrame', mad_k: 'float' = 16, pad_ms: 'float' = 50, smooth_ms: 'float' = 10) -> 'pd.DataFrame'`

```
Per trial, how the pupil-based detector (:func:`detect_blinks`) agrees with the tracker's padded blinks.

``samples`` must have passed :func:`pad_blinks` (tracker blinks padded). Returns one row per trial with
pct_padded_caught (share of padded-blink samples that the detector flags), pct_outside (detector-flagged samples
outside padded blinks, as % of all samples) and pct_speed (speed outliers, % of all samples): Supplementary Note S1.
```

### `interpolate(samples: 'pd.DataFrame', max_gap_ms: 'float' = 1000, kind: 'str' = 'linear', column: 'str' = 'pupil_interp') -> 'pd.DataFrame'`

```
Fill gaps in the cleaned pupil trace that last up to ``max_gap_ms`` (stage 3.2).

Gaps at the start or end of a trial and longer gaps stay missing. ``kind="linear"`` joins the valid samples on
either side of a gap; ``kind="cubic"`` fits a cubic spline through four points spaced one gap length apart, as
described by Mathot et al. (2018), and falls back to linear where those points are missing.

Returns
-------
DataFrame
    The samples with the filled trace in ``column`` (default ``pupil_interp``, so that ``pupil`` keeps the removal
    trace; pass ``column="pupil"`` to replace it).
```

### `data_loss(samples: 'pd.DataFrame', by: 'Optional[str]' = 'version') -> 'Loss'`

```
Data loss and event rates per trial, and their summary by version (stages 3.2 and 3.6).

Parameters
----------
samples : DataFrame
    Samples after :func:`pad_blinks`.
by : str or None
    Column to summarise by (reader means per level, then mean across readers, with a paired t-test of the
    difference when there are two levels).

Returns
-------
Loss
    ``trials``: one row per trial with n_samples, duration_s, pct_invalid, pct_blink_pad (samples lost to the
    padding only), pct_valid, n_blinks, n_saccades, blink_rate and saccade_rate (per s).
    ``by_version``: the summary table (None if ``by`` is None).
```

### `summarise(trials: 'pd.DataFrame', by: 'str' = 'version', columns: 'Iterable[str]' = ('duration_s', 'pct_invalid', 'pct_blink_pad', 'pct_valid', 'blink_rate', 'saccade_rate')) -> 'pd.DataFrame'`

```
Reader means of trial-level ``columns`` per level of ``by``, averaged across readers, with paired tests.
```

### `exclude_trials(samples: 'pd.DataFrame', min_valid: 'float' = 0.5, exclude=None, loss: 'Optional[pd.DataFrame]' = None)`

```
Drop trials with too few valid samples or listed for exclusion (stage 3.2, missing-data threshold).

Parameters
----------
samples : DataFrame
    Samples after :func:`pad_blinks`.
min_valid : float
    Minimum share of valid samples (paper: 0.5, i.e. trials with more than half of their samples missing are
    excluded; 0.75 is the stricter check of Table 3).
exclude : DataFrame, iterable of (reader, trial) or CSV path, optional
    Trials to drop for other reasons decided blind to version (our study: skimmed or incomplete reading).
loss : DataFrame, optional
    The ``trials`` table of :func:`data_loss`, if already computed.

Returns
-------
(DataFrame, DataFrame)
    The remaining samples, and one row per trial with ``excluded`` and ``reason`` columns.
```

## 3.3 Baseline correction

### `reader_means(bins: 'pd.DataFrame', column: 'str' = 'pupil') -> 'pd.Series'`

```
Mean pupil size of each reader over all valid samples (bins weighted by their valid samples).

This is the denominator of the paper's scaling: changes are expressed as a percentage of the reader mean, so that
readers and eyes with different pupil-size units become comparable (Section 3.3).
```

### `baseline(bins: 'pd.DataFrame', window: 'Tuple[float, float]' = (0, 200), method: 'str' = 'subtractive', scale: 'Optional[str]' = 'reader_mean', column: 'Optional[str]' = None, min_valid: 'Optional[float]' = None, means: 'Optional[pd.Series]' = None) -> 'pd.DataFrame'`

```
Baseline correction (stage 3.3; Python 3 of the paper).

Parameters
----------
bins : DataFrame
    Binned trace (:func:`bin`), gaze-corrected first if a correction is used (:func:`correct_gaze`).
window : (start, end)
    Baseline window in ms from text onset (paper: 0 to 200 ms, which ends before the light reflex to the text).
method : {"subtractive", "divisive", "none"}
    ``subtractive``: pupil minus baseline (paper). ``divisive``: change as a percentage of the trial's baseline.
    ``none``: no baseline correction; pupil minus the reader mean.
scale : {"reader_mean", "baseline_mean", None}
    Denominator of subtractive changes: the reader's mean pupil size (paper), the reader's mean baseline, or none
    (raw units).
column : str, optional
    Trace to correct; by default ``pupil_corrected`` if :func:`correct_gaze` was applied, else ``pupil``.
min_valid : float, optional
    Share of valid samples a bin needs (default: the ``ok`` column of :func:`bin`).
means : Series, optional
    Reader means to use (default: :func:`reader_means` of the uncorrected pupil).

Returns
-------
DataFrame
    The bins with ``change`` (per bin), ``baseline`` (per trial, raw units) and ``baseline_pct`` (the baseline as a
    percentage of the reader mean; :func:`low_baselines` flags implausibly small ones).
```

### `low_baselines(data: 'pd.DataFrame', min_pct: 'float' = 60) -> 'pd.DataFrame'`

```
Flag trials whose baseline is implausibly small (stage 3.3; paper: below 60% of the reader mean).

Small baselines come from blinks and other distortions in the baseline window and inflate the corrected values.
The cut-off is best read from a histogram of baselines with log-scaled counts (:func:`plot_baselines`).

Returns
-------
DataFrame
    One row per trial with ``baseline_pct`` and ``low`` (True below ``min_pct``); trials without a baseline are
    listed with ``low`` = True and ``reason`` = "no baseline".
```

## 3.4 Gaze-position correction

### `saccade_steps(bins: 'pd.DataFrame', fixations: 'pd.DataFrame', after: 'Tuple[float, float]' = (20, 120), before: 'float' = 100, late: 'Tuple[float, float]' = (300, 600), max_gap_ms: 'float' = 100, start_after_ms: 'float' = 500, min_fix_ms: 'float' = 80, min_bins: 'int' = 3, min_bins_late: 'int' = 8, means: 'Optional[pd.Series]' = None, classify=classify_saccades) -> 'pd.DataFrame'`

```
Measure the pupil step across every saccade between two retained fixations (stage 3.4).

Parameters
----------
bins : DataFrame
    Binned trace (:func:`bin`) of the kept trials, before baseline correction.
fixations : DataFrame
    Fixation table (:func:`read_fixations`). Saccades are the gaps of 0 to ``max_gap_ms`` between consecutive
    retained fixations (at least ``min_fix_ms``, not bordering a blink); saccade size is the difference between the
    two fixation positions.
after : (start, end)
    Window after landing, in ms, whose mean gives the post-saccade value (paper: 20 to 120 ms).
before : float
    Length of the window before saccade onset (paper: 100 ms).
late : (start, end)
    Later window after landing (300 to 600 ms), for the real response that follows the immediate step.
start_after_ms : float
    Saccades must start at least this long after text onset, and end at least ``late[1]`` before the trial ends.
min_bins, min_bins_late : int
    Valid bins needed in the before/after windows and in the late window.

Returns
-------
DataFrame
    One row per saccade: reader, item, trial, version, eye, type (see :func:`classify_saccades`), x0, y0, x1, y1,
    dx, dy, gap, start (saccade onset = fixation end), landing (next fixation start), ref (pupil before onset, % of
    reader mean), step (after minus before) and late (late window minus before).
```

### `classify_saccades(dx, dy) -> 'np.ndarray'`

```
Saccade type from its horizontal and vertical size in pixels (thresholds for 20-point text, 48 px lines).

forward: |dy| < 20 and 10 < dx <= 200; regression: |dy| < 20 and -200 <= dx < -10; return sweep: 24 <= dy <= 72 and
dx < -200; vertical: |dx| < 100 and 24 <= |dy| <= 120; other: the rest.
```

### `step_slopes(steps: 'pd.DataFrame', by: 'Optional[str]' = 'eye', method: 'str' = 'joint', min_saccades: 'int' = 50, knots=(0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000), reference: 'float' = 500) -> 'pd.DataFrame'`

```
Artifact per pixel of gaze shift, from the saccade steps (stage 3.4).

Parameters
----------
steps : DataFrame
    Output of :func:`saccade_steps`.
by : {"eye", "reader", None}
    Estimate slopes per recorded eye (paper), per reader (readers with more than ``min_saccades`` saccades), or
    pooled.
method : {"joint", "by_type", "map"}
    ``joint``: one regression of the step on horizontal and vertical saccade size over forward saccades,
    regressions and return sweeps (paper). ``by_type`` (exploratory): the horizontal slope from within-line
    saccades only and the vertical slope from vertical saccades only, because return sweeps move gaze left and down
    at once. ``map`` (exploratory): a piecewise-linear map of horizontal position with knots at ``knots`` (the
    knot at ``reference`` fixed at 0) plus a linear vertical slope, fitted to all classified saccades.

Returns
-------
DataFrame
    One row per group: bX and bY (% of the reader mean per pixel), intercept, n_saccades. For ``map``, bX is
    missing and the columns ``x_<knot>`` hold the map (% of the reader mean at each knot).
```

### `regression_slopes(bins: 'pd.DataFrame', window: 'Tuple[float, float]' = (0, 200), min_baseline_pct: 'float' = 60, time_terms: 'bool' = False, means: 'Optional[pd.Series]' = None) -> 'pd.Series'`

```
Artifact slopes from regressing pupil size on gaze position in the reading data (stage 3.4; Table 2).

``time_terms=False``: pooled regression of the baseline-corrected pupil on gaze x and y over all valid bins of the
analysed trials. ``time_terms=True``: within-trial regression with linear and quadratic time, which absorbs the
decline of pupil size during reading. Because gaze covaries with progress through the text, these slopes can absorb
part of a real effect or enlarge it; the saccade steps avoid that (Table 2).

Returns
-------
Series
    bX and bY in pupil units per pixel (the scale of ``bins['pupil']``).
```

### `correct_gaze(bins: 'pd.DataFrame', slopes=None, method: 'Optional[str]' = None, by: 'str' = 'eye', means: 'Optional[pd.Series]' = None, layout=None) -> 'pd.DataFrame'`

```
Remove the gaze-position artifact from every bin, before baseline correction (stage 3.4).

Parameters
----------
bins : DataFrame
    Binned trace (:func:`bin`). Gaze correction must run before :func:`baseline`, so that the baseline is corrected
    for its own gaze position; a warning is raised if the bins already carry a baseline.
slopes : DataFrame or Series
    For ``method="steps"``: :func:`step_slopes` output (% of reader mean per pixel, one row per eye or reader, or
    a horizontal map). For ``method="regression"``: :func:`regression_slopes` output (pupil units per pixel).
method : {None, "steps", "regression", "geometric"}
    None (paper's primary estimate) returns the bins unchanged. "geometric" divides pupil area by cos theta of the
    measured layout (:func:`foreshortening`; Hayes & Petrov, 2016), or pupil diameter by its square root,
    following ``bins.attrs['pupil_unit']``; it needs ``layout`` and no ``slopes``.
by : {"eye", "reader", None}
    Which column of the bins selects the row of ``slopes`` (steps only); None applies one pooled row to all bins.
means : Series, optional
    Reader means for the steps correction (default: :func:`reader_means` of the bins).
layout : str, path or dict, optional
    The measured layout for ``method="geometric"`` (:func:`read_layout`).

Returns
-------
DataFrame
    The bins with ``pupil_corrected`` (and ``cos_theta`` for the geometric correction); missing gaze positions are
    set to the mean gaze position before the artifact is removed. Bins whose eye or reader has no row in ``slopes``
    get a missing corrected value.
```

### `read_layout(layout) -> 'dict'`

```
A measured layout of eye, camera and screen for the geometric correction (stage 3.4; Hayes & Petrov, 2016).

Parameters
----------
layout : str, path or dict
    A CSV file with the columns ``setting`` and ``value``, one row per setting of :data:`LAYOUT_SETTINGS` (other
    columns, such as a unit or a note, are ignored), or a dict with the same keys. ``eye`` (default "left") names
    the point the positions were measured from; the other eye lies ``eye_separation`` mm (default 64) to its side,
    or each eye half of it from the midline.

Returns
-------
dict
    The settings, with numbers as floats.
```

### `foreshortening(bins: 'pd.DataFrame', layout) -> 'np.ndarray'`

```
cos theta for every bin: the factor by which measured pupil area shrinks at the bin's gaze position (stage 3.4).

theta is the angle between the line from the recorded eye to the camera lens and the line from the eye to the gaze
position on the screen (Hayes & Petrov, 2016). Gaze pixels are converted to millimetres on the screen with
the image size of the layout, and each eye's own horizontal position is used (column ``eye``).

Parameters
----------
bins : DataFrame
    Bins (or samples) with ``gaze_x``, ``gaze_y`` (pixels from the upper-left corner) and ``eye``.
layout : str, path or dict
    The measured layout (:func:`read_layout`).

Returns
-------
ndarray
    cos theta per row (missing where the gaze position is missing).
```

### `hat_basis(x, knots) -> 'np.ndarray'`

```
Piecewise-linear (hat) basis of ``x`` at ``knots``: one column per knot, values clamped at the outer knots.
```

## 3.5 Trial length and events

### `trial_means(bins: 'pd.DataFrame', window: 'Tuple[float, Optional[float]]' = (500, 20000), cut_before_keypress_ms: 'float' = 0, min_valid: 'Optional[float]' = None, column: 'str' = 'change', name: 'Optional[str]' = None) -> 'pd.DataFrame'`

```
One value per trial: the mean change in a time window matched across versions (stage 3.5).

Parameters
----------
bins : DataFrame
    Bins after :func:`baseline`.
window : (start, end)
    Window in ms from text onset (paper: 500 to 20,000 ms, the same in every version). ``end=None`` runs to the end
    of the trial (the whole-trial mean, which compares different portions of the slow drift when trial length
    differs between versions).
cut_before_keypress_ms : float
    Leave out the last part of each trial, to check the run-up to the end-of-reading key press (Section 3.5).
min_valid : float, optional
    Share of valid samples a bin needs (default: the ``ok`` column of :func:`bin`).
column : str
    Bin column to average (default ``change``).
name : str, optional
    Name of the output column (default from :func:`window_name`, ``change_0_20s`` for the paper's window).

Returns
-------
DataFrame
    One row per trial with reader, item, trial, version, eye, baseline_pct and the trial measure. Trials without
    valid bins in the window or without a baseline are missing.
```

### `window_name(window, cut_before_keypress_ms: 'float' = 0, prefix: 'str' = 'change') -> 'str'`

```
Column name for a trial measure: ``change_0_20s`` for the paper's 0.5-20 s window, else e.g. ``change_2_20s``.
```

### `event_response(data: 'pd.DataFrame', event: 'Union[str, pd.DataFrame]' = 'blink', window: 'Optional[Tuple[float, float]]' = None, by: 'Optional[str]' = 'version', saccades: 'Optional[pd.DataFrame]' = None, baseline_ms: 'float' = 100, types: 'Sequence[str]' = ('return sweep',), means: 'Optional[pd.Series]' = None, lag_ms: 'float' = 1.0) -> 'Events'`

```
Event-locked pupil responses (stage 3.5; Figure 3C-D of the paper).

Parameters
----------
data : DataFrame
    Samples after :func:`pad_blinks` for ``event="blink"``, ``"saccade"`` or an event table; bins (:func:`bin`) for
    ``event="return_sweep"``.
event : {"blink", "saccade", "return_sweep"} or DataFrame
    ``blink``: locked to the last blink sample; baseline the ``baseline_ms`` before blink onset minus the padding,
    so that the blink's own response is measured. ``saccade``: locked to saccade onset, baseline just before it.
    ``return_sweep``: landing-locked bins of the saccades of ``types`` in ``saccades`` (:func:`saccade_steps`),
    relative to the pupil before saccade onset, as in Figure 3C. A DataFrame with reader, trial and time (ms from
    text onset) locks the samples to those events.
window : (start, end), optional
    Lags in ms around the event (default: -200 to 2,000 ms for blinks, saccades and event tables, as in Figure 3D;
    -300 to 1,000 ms for return sweeps, as in Figure 3C).
by : str or None
    Column to split by (``version``; ``eye`` for return sweeps).
lag_ms : float
    Width of the lag bins of the output (samples are pooled within them), so that readers recorded at different
    sampling rates share one time axis.

Returns
-------
Events
    ``summary``: per level and lag, the mean and SEM across readers of each reader's mean response (% of the
    reader mean), the number of readers, ``pooled`` (all events pooled, raw units) and ``pooled_pct`` (pooled, as
    % of the average reader mean, as in Figure 3D).
    ``by_reader``: per reader, level and lag the sum, count and mean of the responses.
```

## 3.6 Checks and figures

### `plot_trial(samples: 'pd.DataFrame', trial, reader=None, pad_ms: 'float' = 100, bin_ms: 'float' = 20, window: 'Tuple[float, float]' = (0, 200), pupil_range: 'Tuple[float, float]' = (100, 10000), min_valid: 'float' = 0.5, reader_mean: 'Optional[float]' = None, xlim: 'Optional[Tuple[float, float]]' = None)`

```
One trial at four stages of the pipeline (stages 3.1 to 3.3; Figure 2 of the paper).

(A) The raw samples, with the blinks the tracker marked shaded. (B) The samples after each blink is padded by
``pad_ms`` and the padded and invalid samples are removed (:func:`pad_blinks`), with the padded stretches shaded.
(C) The ``bin_ms`` bins (:func:`bin`). (D) The bins after subtractive baseline correction over ``window``, as a
percentage of the reader mean (:func:`baseline`), with the baseline window shaded. The panels run the package's
own functions, so they show exactly what the pipeline does to the trial.

Parameters
----------
samples : DataFrame
    Sample table (:func:`read_eyelink`, :func:`read_csv`), raw or already padded (``pupil_raw`` is then redrawn
    and padded again with ``pad_ms``). Pass all of a reader's trials, so that the reader mean of panel D covers them.
trial : int
    Trial to draw (TRIAL_INDEX).
reader : optional
    Reader to draw, if ``samples`` holds several readers.
pad_ms, bin_ms, window, pupil_range, min_valid
    Settings of :func:`pad_blinks`, :func:`bin` and :func:`baseline` (defaults: the paper's).
reader_mean : float, optional
    Denominator of panel D. By default the mean of the reader's valid samples in ``samples`` after padding
    (:func:`reader_means`); the pipeline takes it over the trials kept after the exclusions.
xlim : (start, end), optional
    Time range in seconds from text onset (default: the whole trial).

Returns
-------
matplotlib Figure
    Four stacked panels sharing the time axis; ``fig.trial_data`` holds the samples and bins drawn.
```

### `plot_overlays(bins: 'pd.DataFrame', column: 'str' = 'change', by: 'Optional[str]' = 'version', readers: 'Optional[Sequence]' = None, max_readers: 'int' = 6, ncols: 'int' = 3)`

```
Trial-level overlays: every trial's trace, one panel per reader, line style by ``by`` (stage 3.6).

Overlays reveal residual artifacts that a summary statistic hides, such as spikes, gaps or implausible trajectories.
```

### `plot_baselines(trials: 'pd.DataFrame', min_pct: 'float' = 60, step: 'float' = 2.5)`

```
Histogram of baselines (% of the reader mean) with counts and log-scaled counts, and the cut-off (stage 3.3).
```

### `plot_grand_mean(bins: 'pd.DataFrame', column: 'str' = 'change', by: 'Optional[str]' = 'version', bin_s: 'float' = 1.0, max_s: 'float' = 40, min_readers: 'int' = 20, min_baseline_pct: 'Optional[float]' = 60, ax=None)`

```
Grand-mean time course by version with 95% confidence intervals across readers (Figure 3B of the paper).

Bins are averaged per reader in ``bin_s`` steps, then across readers; points with fewer than ``min_readers``
readers are not drawn, so uneven trial lengths do not produce spurious divergence at the end of trials.
```

### `plot_quality(trials: 'pd.DataFrame', by: 'str' = 'version', measures: 'Sequence[str]' = ('pct_valid', 'pct_invalid', 'pct_blink_pad', 'blink_rate', 'saccade_rate'))`

```
Data loss and blink and saccade rates by version: reader means joined across versions (stage 3.6).
```

### `plot_gaze(bins: 'pd.DataFrame', by: 'str' = 'version', relative_to_baseline: 'bool' = True, window=(500, 20000), baseline_window=(0, 200))`

```
Mean gaze position by version (stage 3.6): reader means of horizontal and vertical gaze, optionally relative to
the gaze position in the baseline window, which shows where versions differ in the gaze artifact (Section 3.4).
```

## 3.7 Control predictors and export for R

### `add_covariates(bins: 'pd.DataFrame', fixations: 'Optional[pd.DataFrame]' = None, center: 'Tuple[float, float]' = (512, 384), px_per_degree: 'Optional[float]' = None, time_center_s: 'float' = 10.0, min_fix_ms: 'float' = 80) -> 'pd.DataFrame'`

```
Add generic control predictors to the bins.

Adds ``time_s`` (s from text onset), ``time2`` ((time_s - time_center_s) squared), ``eccentricity`` (distance of
gaze from ``center``, pixels) and, if ``fixations`` are given, ``fix_duration`` (duration of the fixation in
progress, i.e. the last retained fixation that started at or before the bin) and ``next_distance`` (distance to the
next fixation, in degrees if ``px_per_degree`` is given, else pixels). Study-specific predictors, such as local text
density computed from interest areas, can be added as further columns.
```

### `control_predictors(bins: 'pd.DataFrame', covariates: 'Sequence[str]', window: 'Tuple[float, float]' = (500, 20000), min_baseline_pct: 'Optional[float]' = 60, column: 'str' = 'change', name: 'str' = 'change_adjusted', complete_cases: 'Optional[Sequence[str]]' = None)`

```
Trial means adjusted for control predictors estimated within trials (Section 3.7).

Parameters
----------
bins : DataFrame
    Bins after :func:`baseline` with the covariate columns (see :func:`add_covariates`).
covariates : list of str
    Columns to partial out. Bins with a missing value in any of them are left out, so the unadjusted mean on the
    same bins is returned too.
window : (start, end)
    Window in ms from text onset.
min_baseline_pct : float or None
    Analysed trials only (baseline at least this % of the reader mean), as in the paper.
complete_cases : list of str, optional
    Columns that must be present for a bin to be used (default: ``covariates`` and gaze position). Pass the
    largest covariate set to compare nested adjustments on the same bins, as in the paper.

Returns
-------
(DataFrame, Series)
    One row per trial with the unadjusted mean on the bins used (``change_same_bins``) and the adjusted mean
    (``name``); and the within-trial slopes.
```

### `export_for_r(trials: 'pd.DataFrame', bins: 'pd.DataFrame', folder: 'str' = 'for_R', bin_ms: 'float' = 100, window: 'Tuple[float, float]' = (500, 20000), reference: 'Optional[str]' = None, scripts: 'bool' = True, options: 'Optional[pd.DataFrame]' = None, config=None) -> 'dict'`

```
Write the files for the models in R (stage 3.7): trials.csv, bins.csv and, for options tables, options.csv.

Parameters
----------
trials : DataFrame
    One row per trial: :func:`trial_means` output or :func:`options_table`. Must contain reader, item, version and
    baseline_pct; ``change_0_20s`` (the paper's primary measure) is what ``lmm.R`` models.
bins : DataFrame
    Bins after :func:`baseline` (20 ms), averaged here into ``bin_ms`` bins within ``window`` for ``gamm.R``.
folder : str
    Output folder (created if needed).
bin_ms : float
    Bin size of the trace for the time-course model (paper: 100 ms).
window : (start, end)
    Time window of the trace, ms from text onset (paper: 500 to 20,000 ms).
reference : str, optional
    Version coded 0 in the ``contrast`` column (default: the first version in alphabetical order, which is
    "non-simplified" in the paper); the other version is coded 1.
scripts : bool
    Copy lmm.R, gamm.R and multiverse.R into ``folder``, so that they run there without editing.
options : DataFrame, optional
    Model table for multiverse.R (default: ``trials.attrs["options"]`` from :func:`options_table`).

Returns
-------
dict
    Paths of the files written.

Notes
-----
All trials with a baseline are written; the R scripts keep those whose baseline is at least ``MIN_BASE`` (60) %
of the reader mean, as in the paper. In an options table each option column already leaves out the trials that
the option excludes.
```

### `gamm_bins(bins: 'pd.DataFrame', bin_ms: 'float' = 100, window: 'Tuple[float, float]' = (500, 20000), column: 'str' = 'change') -> 'pd.DataFrame'`

```
Average the 20 ms bins of every trial in ``bin_ms`` bins within ``window`` (the trace for gamm.R).

Only bins with enough valid samples enter (the ``ok`` column of :func:`bin`); pupil change and gaze position are
their means. ``time`` is the bin centre in seconds from text onset.
```

### `r_script_path(name: 'str') -> 'str'`

```
Path of one of the R scripts installed with the package (``lmm.R``, ``gamm.R`` or ``multiverse.R``).
```

## 5 The estimate under each option

### `options_table(samples, options: 'Optional[Mapping]' = None, fixations: 'Optional[pd.DataFrame]' = None, config=None, steps: 'Optional[pd.DataFrame]' = None, trials: 'Optional[pd.DataFrame]' = None) -> 'pd.DataFrame'`

```
The trial measure under each option, one column per option, for the R multiverse script (Section 5).

Parameters
----------
samples : DataFrame or PupilData
    The sample table of one or more readers (:func:`read_eyelink`), which is prepared with the settings of
    ``config`` (:func:`prepare`), or data already prepared by :func:`prepare` or :func:`run_pipeline`.
options : dict, optional
    Option name (the output column) -> settings, as in :data:`PAPER_OPTIONS` (the default: the options of Tables 3
    and S2). Each option changes one decision of the primary estimate; settings not named keep the primary choice.
    The geometric gaze correction is left out unless the config (``gaze.layout``) or the option gives a layout.
fixations : DataFrame, optional
    Fixation table (:func:`read_fixations`), for the fixation-level and step-based options.
config : dict or str, optional
    Pipeline settings (see :func:`run_pipeline`); the primary baseline window, analysis window and low-baseline
    cut-off are taken from it.
steps : DataFrame, optional
    Saccade steps (:func:`saccade_steps`), if already computed.
trials : DataFrame, optional
    Trial table with pct_valid, duration_s, blink_rate and saccade_rate (``data_loss().trials``), if not part of
    the prepared data.

Returns
-------
DataFrame
    One row per trial with a baseline: reader, item, trial, version, eye, baseline_pct, pct_valid, duration_s,
    blink_rate, saccade_rate, the standardised covariates duration_z, blink_z, saccade_z (over all trials),
    baseline_z (over the analysed trials) and eye_c (left +0.5, right -0.5), and one column per option with the
    trial measure under that option (missing for the trials it leaves out). Analysed trials have a primary
    baseline of at least ``min_pct`` of the reader mean (60%), for every option except ``low_baselines_kept``.
    ``attrs["options"]`` holds :func:`options_spec`.
```

### `options_spec(options: 'Optional[Mapping]' = None) -> 'pd.DataFrame'`

```
One row per option: output column, label, model (random part, covariates, tested term), section and table.

This is the table that ``multiverse.R`` reads (``options.csv``) to fit one model per option column.
```

## Pipeline

### `run_pipeline(path, config=None, out: 'Optional[str]' = None, cache: 'Optional[str]' = None, verbose: 'bool' = True) -> 'Result'`

```
Run the whole pipeline from the reports under ``path`` and write the files for R (the paper's quick start).

Parameters
----------
path : str
    A sample report, or a folder searched for the reports of every reader (see :func:`find_readers`). None reads
    prepared readers from ``cache`` only.
config : dict or str, optional
    Settings, as a dict or a YAML/JSON file; :data:`DEFAULTS` are the paper's primary choices.
out : str, optional
    Output folder (default: ``pupilread_output`` next to ``path``). The R files go to ``out/<export.folder>``,
    tables to ``out/tables`` and check plots to ``out/figures``.
cache : str, optional
    Folder for per-reader prepared data (see :func:`prepare_readers`).

Returns
-------
Result
    The tables of every stage and the list of files written.
```

### `load_config(config=None) -> 'dict'`

```
The default settings (:data:`DEFAULTS`) updated with ``config``: a dict, or a path to a YAML or JSON file.

Unknown settings raise an error, so that a misspelt key cannot silently leave the default in place.
```

### `default_config_yaml() -> 'str'`

```
The default settings as YAML text (``pupilread config`` prints it).
```

### `find_readers(path, config=None) -> 'List[dict]'`

```
The sample report (and the message and fixation reports beside it) of every reader under ``path``.

Sample reports are files whose names contain "sample"; message and fixation reports are files in the same folder
whose names contain "mess" and "fix". The reader ID is taken from ``config["data"]["reader_pattern"]`` (a regular
expression with one group, applied to the path) if given, else from the name of the folder holding the report
(folder names such as "Output" are skipped), else from the file name.

Returns
-------
list of dict
    One dict per reader with keys reader, samples, messages and fixations (paths or None).
```

### `read_reader(job: 'Mapping', config=None)`

```
Read one reader's samples and fixations as :func:`find_readers` lists them.
```

### `prepare(samples: 'pd.DataFrame', fixations: 'Optional[pd.DataFrame]' = None, config=None, exclude=None, options: 'Optional[Mapping]' = None) -> 'PupilData'`

```
Stages 3.1-3.2 for the readers in ``samples``: blinks, interpolation, data loss, exclusion, bins and levels.

Parameters
----------
samples : DataFrame
    Sample table (:func:`read_eyelink` or :func:`read_csv`).
fixations : DataFrame, optional
    Fixation table (:func:`read_fixations`); needed for :func:`compare_levels`, the saccade steps and the
    fixation-level option.
config : dict or str, optional
    Settings (see :data:`DEFAULTS`).
exclude : DataFrame, iterable or CSV path, optional
    Trials to drop before analysis (default: ``config["data"]["exclude"]``).
options : dict, optional
    Options (see :func:`options_table`); options with ``samples`` settings get their own bins.
```

### `prepare_readers(path, config=None, cache: 'Optional[str]' = None, verbose: 'bool' = True) -> 'PupilData'`

```
Read and prepare every reader under ``path`` one at a time (see :func:`find_readers` and :func:`prepare`).

With ``cache``, each reader's prepared data are written to ``cache/<reader>`` and read back on later runs, so an
interrupted run resumes and the pooled stages can run on another machine without the raw reports.
```

### `analyse(data: 'PupilData', config=None) -> 'Result'`

```
Stages 3.3-3.6 on prepared data: gaze correction, baseline, low baselines, trial means, events and options.
```

### `levels_summary(levels: 'Optional[pd.DataFrame]', trials: 'Optional[pd.DataFrame]' = None) -> 'dict'`

```
Agreement of fixation-report and sample pupil values over fixations, and the share of reading time covered.
```

### `summarise_events(by_reader: 'Optional[pd.DataFrame]', by: 'str' = 'version') -> 'Optional[Events]'`

```
Pool event-locked responses prepared per reader (``PupilData.blink_events``) into the summary table.
```

### `PupilData(bins: 'pd.DataFrame', trials: 'pd.DataFrame', fixations: 'Optional[pd.DataFrame]' = None, levels: 'Optional[pd.DataFrame]' = None, blink_events: 'Optional[pd.DataFrame]' = None, option_bins: 'dict' = <factory>) -> None`

```
Prepared data of one or more readers (stages 3.1-3.2).

Attributes
----------
bins : DataFrame
    20 ms bins of the kept trials (:func:`bin`), with ``pupil`` (blinks removed) and ``pupil_interp``.
trials : DataFrame
    One row per trial read: data loss, event rates, and ``excluded`` with its ``reason`` (:func:`exclude_trials`).
fixations : DataFrame or None
    Fixation table of the kept trials (:func:`read_fixations`).
levels : DataFrame or None
    Per retained fixation, the fixation-report pupil and the mean of the samples inside it (:func:`compare_levels`).
blink_events : DataFrame or None
    Blink-locked responses per reader, version and lag (``by_reader`` of :func:`event_response`).
option_bins : dict
    Bins prepared with other sample-level settings, one entry per option that changes them.
```

## Example data

### `make_example(folder: 'str' = 'pupilread_example', n_readers: 'int' = 3, n_items: 'int' = 4, n_lines: 'int' = 10, words_per_line: 'int' = 12, hz: 'float' = 1000.0, seed: 'int' = 2026, onset_ms: 'float' = 1000.0) -> 'dict'`

```
Write synthetic Data Viewer sample, message and fixation reports for a small study, with design.csv.

Each reader reads ``n_items`` passages, half in each version ("simplified" or "non-simplified", counterbalanced
across readers). One trial per study loses most of its samples (to exercise trial exclusion) and one has a
distorted baseline (to exercise the low-baseline check).

Returns
-------
dict
    Paths: ``folder``, ``design`` (design.csv), ``exclusions`` (exclusions.csv, one trial flagged as skimmed),
    ``layout`` (layout.csv, an invented layout of eye, camera and screen for the geometric correction; the
    simulated artifact does not follow it) and ``readers`` (one dict per reader with its three reports).
```
