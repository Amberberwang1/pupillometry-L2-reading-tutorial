"""
Pupillometry Preprocessing Pipeline
Supplementary materials for: "Pupillometry for L2 reading research:
A step-by-step tutorial for eye-tracking researchers"

This script implements the six-stage pipeline described in Section 3:
  Stage 1 — Blink handling (Section 3.1)
  Stage 2 — Fixation filtering (Section 3.2)
  Stage 3 — Baseline correction (Section 3.3)
  Stage 4 — Gaze-position correction (Section 3.4)
  Stage 5 — Data quality checks and visualisation (Section 3.5)
  Stage 6 — Statistical modelling (Section 3.6)

Key methodological references:
  Mathôt & Vilotijević (2023). Methods in cognitive pupillometry.
  van Rij et al. (2019). Analyzing the time course of pupillometric data.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# Set style for publication-quality figures (Georgia, Word-style)
plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams['font.family'] = 'Georgia'
sns.set_palette("colorblind")

# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_DIR = Path("eye-tracking data")  # folder with the study data (local path removed for review)
DATA_DIR = BASE_DIR / "eye-tracking data" / "Evs_files"

# Preprocessing parameters (following van Rij et al., 2019)
BASELINE_WINDOW_MS = 500  # First 500ms of trial for baseline
MIN_FIXATION_DURATION = 80  # Minimum fixation duration in ms
MIN_PUPIL_SIZE = 100  # Minimum plausible pupil size
MAX_PUPIL_SIZE = 10000  # Maximum plausible pupil size
TIME_BIN_SIZE = 5000  # Time bin size in ms for time-course analysis

# =============================================================================
# DATA LOADING FUNCTIONS
# =============================================================================

def get_condition_mapping():
    """Return the condition mapping for Block B participants."""
    return {
        '01': 'ns', '02': 'ss', '03_a': 'ss', '03_b': 'ns',
        '04_ss': 'ss', '04_ns': 'ns', '05_SS': 'ss', '05_ns': 'ns',
        '06_SS': 'ss', '06_NS': 'ns'
    }

def load_fixation_report(filepath):
    """Load a single fixation report file."""
    try:
        df = pd.read_csv(filepath, sep=',', low_memory=False)
        return df
    except:
        try:
            df = pd.read_csv(filepath, sep='\t', low_memory=False)
            return df
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
            return None

def load_all_fixation_data():
    """Load all fixation data from both blocks.
    
    Block A: Use 'condition' column from data — each participant has both BS and BN trials.
    So BS and BN each have data from all participants (5 or 6).
    Block B: SS and NS from separate files per participant; 5 participants have both.
    """
    all_data = []
    
    EXCLUDED_PARTICIPANTS = []
    # Block A: exclude one participant so we have 5 (BS and BN each from 5). P3 excluded.
    BLOCK_A_EXCLUDE = ['03']
    
    def _add_block_a(df, filepath, pid, fname):
        """Add Block A dataframe; use condition column from file (each participant has BS and BN trials)."""
        df = df.copy()
        df['block'] = 'A'
        df['participant'] = pid
        if 'condition' in df.columns and df['condition'].notna().any():
            # Use condition from data — file has BS/BN per trial
            c = df['condition'].astype(str).str.strip().str.upper()
            df['condition'] = c.where(c.isin(['BS', 'BN']))
        else:
            df['condition'] = 'BS' if pid in ('01', '03', '05') else 'BN'
        if pid in EXCLUDED_PARTICIPANTS or pid in BLOCK_A_EXCLUDE:
            if pid in BLOCK_A_EXCLUDE:
                print(f"  SKIPPED Block A participant {fname} (Block A: 5 participants)")
            return
        all_data.append(df)
        print(f"  Loaded Block A participant {fname}")
    
    # Block A files - participants 03-06
    block_a_dir = DATA_DIR / "Block_A_03_06_evs" / "Output"
    if block_a_dir.exists():
        for pattern in ["Fixation*", "fixation*"]:
            for filepath in block_a_dir.glob(pattern):
                df = load_fixation_report(filepath)
                if df is not None:
                    fname = filepath.stem
                    pid = None
                    if '03' in fname: pid = '03'
                    elif '04' in fname: pid = '04'
                    elif '05' in fname: pid = '05'
                    elif '06' in fname: pid = '06'
                    if pid and pid not in EXCLUDED_PARTICIPANTS:
                        _add_block_a(df, filepath, pid, fname)
    
    # Block A files - participants 01-02
    block_a_alt = DATA_DIR / "Block_A_01_02_evs"
    if block_a_alt.exists():
        for pattern in ["**/*Fixation*", "**/*fixation*"]:
            for filepath in block_a_alt.glob(pattern):
                df = load_fixation_report(filepath)
                if df is not None:
                    fname = filepath.stem
                    pid = '01' if '01' in fname else '02' if '02' in fname else None
                    if pid and pid not in EXCLUDED_PARTICIPANTS:
                        _add_block_a(df, filepath, pid, fname)
    
    # Block B files
    block_b_dirs = [
        DATA_DIR / "Block_B_01_evs" / "Output",
        DATA_DIR / "Block_B_02_evs" / "Output",
        DATA_DIR / "Block_B_03-06_evs" / "Output"
    ]
    
    condition_map = get_condition_mapping()
    
    for block_dir in block_b_dirs:
        if block_dir.exists():
            # Try both uppercase and lowercase patterns
            for pattern in ["Fixation*", "fixation*"]:
                for filepath in block_dir.glob(pattern):
                    df = load_fixation_report(filepath)
                    if df is not None:
                        df['block'] = 'B'
                        fname = filepath.stem.lower()
                        
                        # Determine condition based on filename
                        if 'ss' in fname:
                            df['condition'] = 'SS'
                        elif 'ns' in fname:
                            df['condition'] = 'NS'
                        elif '_a' in fname:
                            df['condition'] = 'SS'  # a = ss
                        elif '_b' in fname:
                            df['condition'] = 'NS'  # b = ns
                        else:
                            # Default based on file structure
                            df['condition'] = 'SS'
                        
                        # Extract participant ID
                        extracted_pid = None
                        for pid in ['01', '02', '03', '04', '05', '06']:
                            if pid in fname:
                                df['participant'] = pid
                                extracted_pid = pid
                                break
                        
                        # Skip excluded participants (Block B: exclude P1 so SS and NS each have 5 participants)
                        if extracted_pid in EXCLUDED_PARTICIPANTS:
                            print(f"  SKIPPED Block B participant {fname} (excluded)")
                            continue
                        BLOCK_B_EXCLUDE = ['01']  # P1 has only SS in Block B; exclude so SS & NS each have 5 (P2–P6)
                        if extracted_pid in BLOCK_B_EXCLUDE:
                            print(f"  SKIPPED Block B participant {fname} (Block B: use 5 participants for SS & NS)")
                            continue
                        
                        all_data.append(df)
                        print(f"  Loaded Block B participant {fname}")
    
    if all_data:
        combined = pd.concat(all_data, ignore_index=True)
        print(f"Loaded {len(combined)} fixations from {len(all_data)} files")
        return combined
    else:
        print("No data loaded!")
        return None

# =============================================================================
# PREPROCESSING FUNCTIONS (Following van Rij et al., 2019)
# =============================================================================

def remove_artifacts(df):
    """
    Remove artifact fixations following van Rij et al. (2019):
    1. Blink-affected fixations
    2. Fixations with extreme pupil values
    3. Very short fixations
    """
    n_original = len(df)
    
    # Identify pupil column
    pupil_col = None
    for col in ['CURRENT_FIX_PUPIL', 'pupil', 'PUPIL_SIZE']:
        if col in df.columns:
            pupil_col = col
            break
    
    if pupil_col is None:
        print("Warning: No pupil column found!")
        return df
    
    # Convert pupil to numeric
    df[pupil_col] = pd.to_numeric(df[pupil_col], errors='coerce')
    
    # 1. Remove blink-affected fixations
    if 'CURRENT_FIX_BLINK_AROUND' in df.columns:
        blink_mask = df['CURRENT_FIX_BLINK_AROUND'].isin(['BEFORE', 'AFTER', 'BOTH'])
        n_blinks = blink_mask.sum()
        df = df[~blink_mask]
        print(f"  Removed {n_blinks} blink-adjacent fixations")
    
    # 2. Remove extreme pupil values
    extreme_mask = (df[pupil_col] < MIN_PUPIL_SIZE) | (df[pupil_col] > MAX_PUPIL_SIZE)
    n_extreme = extreme_mask.sum()
    df = df[~extreme_mask]
    print(f"  Removed {n_extreme} extreme pupil values")
    
    # 3. Remove very short fixations
    duration_col = None
    for col in ['CURRENT_FIX_DURATION', 'duration', 'DURATION']:
        if col in df.columns:
            duration_col = col
            break
    
    if duration_col:
        df[duration_col] = pd.to_numeric(df[duration_col], errors='coerce')
        short_mask = df[duration_col] < MIN_FIXATION_DURATION
        n_short = short_mask.sum()
        df = df[~short_mask]
        print(f"  Removed {n_short} short fixations (<{MIN_FIXATION_DURATION}ms)")
    
    # 4. Remove missing pupil values
    missing_mask = df[pupil_col].isna()
    n_missing = missing_mask.sum()
    df = df[~missing_mask]
    print(f"  Removed {n_missing} missing pupil values")
    
    n_final = len(df)
    print(f"  Total: {n_original} -> {n_final} fixations ({100*n_final/n_original:.1f}% retained)")
    
    return df

def calculate_baseline(df):
    """
    Calculate baseline pupil size per trial.
    Following van Rij et al.: "baseline as average pupil dilation in time window
    of 250ms... before the auditory stimuli started"
    
    For reading: Use first BASELINE_WINDOW_MS of each trial.
    """
    # Identify key columns
    pupil_col = 'CURRENT_FIX_PUPIL' if 'CURRENT_FIX_PUPIL' in df.columns else None
    start_col = 'CURRENT_FIX_START' if 'CURRENT_FIX_START' in df.columns else None
    trial_start_col = 'TRIAL_START_TIME' if 'TRIAL_START_TIME' in df.columns else None
    
    if pupil_col is None or start_col is None:
        print("Warning: Required columns not found for baseline calculation")
        return df
    
    # Convert to numeric
    df[pupil_col] = pd.to_numeric(df[pupil_col], errors='coerce')
    df[start_col] = pd.to_numeric(df[start_col], errors='coerce')
    if trial_start_col and trial_start_col in df.columns:
        df[trial_start_col] = pd.to_numeric(df[trial_start_col], errors='coerce')
    
    # Calculate time from trial onset (per trial within each block and condition)
    # Block B: same (participant, TRIAL_INDEX, block) can be SS or NS (separate files) → include condition for 16 trials/participant
    group_cols = ['participant', 'TRIAL_INDEX', 'block', 'condition'] if 'block' in df.columns and 'condition' in df.columns else ['participant', 'TRIAL_INDEX']
    df['time_in_trial'] = df.groupby(group_cols)[start_col].transform(
        lambda x: x - x.min()
    )
    
    # Calculate baseline per trial (80 Block A + 80 Block B = 160 for 5+5 participants; Block A 8 BS + 8 BN per person, Block B 8 SS + 8 NS per person)
    baseline_data = df[df['time_in_trial'] <= BASELINE_WINDOW_MS].groupby(
        group_cols
    )[pupil_col].mean().reset_index()
    baseline_data.columns = list(group_cols) + ['baseline_pupil']
    
    # Merge baseline back
    df = df.merge(baseline_data, on=group_cols, how='left')
    
    # Fill missing baselines with condition mean
    if df['baseline_pupil'].isna().any():
        condition_baseline = df.groupby('condition')['baseline_pupil'].transform('mean')
        df['baseline_pupil'] = df['baseline_pupil'].fillna(condition_baseline)
    
    print(f"  Calculated baseline for {len(baseline_data)} trials")
    print(f"  Mean baseline: {df['baseline_pupil'].mean():.2f}")
    
    return df

def apply_baseline_correction(df):
    """
    Apply subtractive baseline correction.
    Following van Rij et al.: "baseline value is simply subtracted from the
    measured pupil dilation"
    """
    pupil_col = 'CURRENT_FIX_PUPIL' if 'CURRENT_FIX_PUPIL' in df.columns else None
    
    if pupil_col and 'baseline_pupil' in df.columns:
        df['pupil_baselined'] = df[pupil_col] - df['baseline_pupil']
        
        # Also calculate proportional change (for reference)
        df['pupil_normalized'] = (df[pupil_col] - df['baseline_pupil']) / df['baseline_pupil'] * 100
        
        print(f"  Applied baseline correction")
        print(f"  Mean baselined pupil: {df['pupil_baselined'].mean():.2f}")
    
    return df

def apply_gaze_correction(df):
    """
    Apply gaze position correction.
    Following van Rij et al.: "When gaze shifting cannot be prevented, the
    observed pupillary response should be corrected for gaze-dependent fluctuations"
    
    Uses regression to remove gaze-dependent pupil variation.
    """
    pupil_col = 'pupil_baselined' if 'pupil_baselined' in df.columns else 'CURRENT_FIX_PUPIL'
    x_col = 'CURRENT_FIX_X' if 'CURRENT_FIX_X' in df.columns else None
    y_col = 'CURRENT_FIX_Y' if 'CURRENT_FIX_Y' in df.columns else None
    
    if x_col is None or y_col is None:
        print("Warning: Gaze position columns not found")
        return df
    
    # Convert to numeric
    df[x_col] = pd.to_numeric(df[x_col], errors='coerce')
    df[y_col] = pd.to_numeric(df[y_col], errors='coerce')
    
    # Remove rows with missing gaze data
    valid_mask = df[x_col].notna() & df[y_col].notna() & df[pupil_col].notna()
    
    if valid_mask.sum() < 100:
        print("Warning: Not enough valid data for gaze correction")
        df['pupil_corrected'] = df[pupil_col]
        return df
    
    # Fit regression: Pupil ~ X + Y
    X = df.loc[valid_mask, [x_col, y_col]].values
    y = df.loc[valid_mask, pupil_col].values
    
    # Add intercept
    X_with_intercept = np.column_stack([np.ones(len(X)), X])
    
    # Solve least squares
    try:
        coeffs, residuals, rank, s = np.linalg.lstsq(X_with_intercept, y, rcond=None)
        
        # Calculate corrected pupil (residuals + mean)
        predicted = X_with_intercept @ coeffs
        df.loc[valid_mask, 'pupil_corrected'] = y - predicted + y.mean()
        
        # Fill non-valid with uncorrected values
        df['pupil_corrected'] = df['pupil_corrected'].fillna(df[pupil_col])
        
        print(f"  Applied gaze position correction")
        print(f"  Gaze coefficients: X={coeffs[1]:.4f}, Y={coeffs[2]:.4f}")
        
    except Exception as e:
        print(f"Warning: Gaze correction failed: {e}")
        df['pupil_corrected'] = df[pupil_col]
    
    return df

def remove_pupil_outliers(df, sd_threshold=4.0, participant_sd_thresholds=None):
    """
    Remove pupil outliers using per-participant SD-based threshold.
    participant_sd_thresholds: dict e.g. {3: 2.5} = P03 uses 2.5 SD (moderate); others use sd_threshold.
    SS and NS (Block B) are not modified separately; same rule per participant.
    """
    pupil_col = 'pupil_corrected' if 'pupil_corrected' in df.columns else 'pupil_baselined'
    
    if pupil_col not in df.columns:
        print("Warning: No pupil column found for outlier removal")
        return df
    
    n_original = len(df)
    if participant_sd_thresholds is None:
        participant_sd_thresholds = {}

    def remove_outliers_per_participant(group):
        pid = group.name
        thresh = participant_sd_thresholds.get(pid, sd_threshold)
        mean_val = group[pupil_col].mean()
        std_val = group[pupil_col].std()
        if std_val == 0 or pd.isna(std_val):
            return group
        lower = mean_val - thresh * std_val
        upper = mean_val + thresh * std_val
        return group[(group[pupil_col] >= lower) & (group[pupil_col] <= upper)]

    df = df.groupby('participant', group_keys=False).apply(remove_outliers_per_participant)

    n_removed = n_original - len(df)
    print(f"  Removed {n_removed} outliers ({n_removed/n_original*100:.1f}%)")
    if participant_sd_thresholds:
        p3_sd = participant_sd_thresholds.get(3, sd_threshold)
        print(f"  P03 only: {p3_sd} SD (minimal); others: no removal")
    
    return df

def create_time_bins(df):
    """Create time bins for time-course analysis."""
    if 'time_in_trial' not in df.columns:
        print("Warning: time_in_trial not found, cannot create time bins")
        return df
    
    # Create time bins
    df['time_bin'] = (df['time_in_trial'] // TIME_BIN_SIZE) * TIME_BIN_SIZE
    df['time_bin_label'] = df['time_bin'].apply(
        lambda x: f"{int(x/1000)}-{int((x+TIME_BIN_SIZE)/1000)}s"
    )
    
    print(f"  Created {df['time_bin'].nunique()} time bins of {TIME_BIN_SIZE}ms")
    
    return df

# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================

def aggregate_by_trial(df):
    """Aggregate pupil data to trial level."""
    pupil_col = 'pupil_corrected' if 'pupil_corrected' in df.columns else 'pupil_baselined'
    if pupil_col not in df.columns:
        pupil_col = 'CURRENT_FIX_PUPIL'
    
    agg_cols = {
        pupil_col: ['mean', 'std', 'median'],
        'time_in_trial': 'max'
    }
    
    if 'baseline_pupil' in df.columns:
        agg_cols['baseline_pupil'] = 'first'
    
    trial_data = df.groupby(['participant', 'TRIAL_INDEX', 'block', 'condition']).agg(
        agg_cols
    ).reset_index()
    
    # Flatten column names
    trial_data.columns = ['_'.join(col).strip('_') if isinstance(col, tuple) else col 
                         for col in trial_data.columns]
    
    return trial_data

def aggregate_by_time_bin(df):
    """Aggregate pupil data by condition and time bin."""
    pupil_col = 'pupil_corrected' if 'pupil_corrected' in df.columns else 'pupil_baselined'
    if pupil_col not in df.columns:
        pupil_col = 'CURRENT_FIX_PUPIL'
    
    # Calculate mean and SE per condition and time bin
    time_course = df.groupby(['block', 'condition', 'time_bin']).agg({
        pupil_col: ['mean', 'std', 'count']
    }).reset_index()
    
    time_course.columns = ['block', 'condition', 'time_bin', 'mean', 'std', 'count']
    time_course['se'] = time_course['std'] / np.sqrt(time_course['count'])
    time_course['ci95'] = 1.96 * time_course['se']
    
    return time_course

def run_statistical_tests(df):
    """Run statistical tests comparing conditions."""
    results = {}
    
    pupil_col = 'pupil_corrected' if 'pupil_corrected' in df.columns else 'pupil_baselined'
    if pupil_col not in df.columns:
        pupil_col = 'CURRENT_FIX_PUPIL'
    
    # Block A: BS vs BN
    block_a = df[df['block'] == 'A']
    if len(block_a) > 0:
        bs_data = block_a[block_a['condition'] == 'BS'][pupil_col].dropna()
        bn_data = block_a[block_a['condition'] == 'BN'][pupil_col].dropna()
        
        if len(bs_data) > 0 and len(bn_data) > 0:
            t_stat, p_val = stats.ttest_ind(bs_data, bn_data)
            cohens_d = (bs_data.mean() - bn_data.mean()) / np.sqrt(
                ((len(bs_data)-1)*bs_data.std()**2 + (len(bn_data)-1)*bn_data.std()**2) / 
                (len(bs_data) + len(bn_data) - 2)
            )
            
            results['Block_A'] = {
                'BS_mean': bs_data.mean(),
                'BS_sd': bs_data.std(),
                'BS_n': len(bs_data),
                'BN_mean': bn_data.mean(),
                'BN_sd': bn_data.std(),
                'BN_n': len(bn_data),
                't_statistic': t_stat,
                'p_value': p_val,
                'cohens_d': cohens_d,
                'df': len(bs_data) + len(bn_data) - 2
            }
    
    # Block B: SS vs NS
    block_b = df[df['block'] == 'B']
    if len(block_b) > 0:
        ss_data = block_b[block_b['condition'] == 'SS'][pupil_col].dropna()
        ns_data = block_b[block_b['condition'] == 'NS'][pupil_col].dropna()
        
        if len(ss_data) > 0 and len(ns_data) > 0:
            t_stat, p_val = stats.ttest_ind(ss_data, ns_data)
            cohens_d = (ss_data.mean() - ns_data.mean()) / np.sqrt(
                ((len(ss_data)-1)*ss_data.std()**2 + (len(ns_data)-1)*ns_data.std()**2) / 
                (len(ss_data) + len(ns_data) - 2)
            )
            
            results['Block_B'] = {
                'SS_mean': ss_data.mean(),
                'SS_sd': ss_data.std(),
                'SS_n': len(ss_data),
                'NS_mean': ns_data.mean(),
                'NS_sd': ns_data.std(),
                'NS_n': len(ns_data),
                't_statistic': t_stat,
                'p_value': p_val,
                'cohens_d': cohens_d,
                'df': len(ss_data) + len(ns_data) - 2
            }
    
    return results

# =============================================================================
# VISUALIZATION FUNCTIONS
# =============================================================================

def plot_time_course(df, save_path=None):
    """
    Plot pupil time course by condition.
    Following van Rij et al. Figure 4 style.
    """
    pupil_col = 'pupil_corrected' if 'pupil_corrected' in df.columns else 'pupil_baselined'
    if pupil_col not in df.columns:
        pupil_col = 'CURRENT_FIX_PUPIL'
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Block A
    block_a = df[df['block'] == 'A']
    if len(block_a) > 0 and 'time_bin' in block_a.columns:
        time_course_a = aggregate_by_time_bin(block_a)
        
        for cond in ['BS', 'BN']:
            cond_data = time_course_a[time_course_a['condition'] == cond]
            if len(cond_data) > 0:
                axes[0].plot(cond_data['time_bin']/1000, cond_data['mean'], 
                           label=cond, linewidth=2)
                axes[0].fill_between(cond_data['time_bin']/1000,
                                   cond_data['mean'] - cond_data['ci95'],
                                   cond_data['mean'] + cond_data['ci95'],
                                   alpha=0.3)
        
        axes[0].set_xlabel('Time from Trial Onset (seconds)', fontsize=12)
        axes[0].set_ylabel(f'Pupil Size (baselined)', fontsize=12)
        axes[0].set_title('Block A: BS vs BN', fontsize=14, fontweight='bold')
        axes[0].legend(title='Condition')
        axes[0].axhline(y=0, color='gray', linestyle='--', alpha=0.5)
    
    # Block B
    block_b = df[df['block'] == 'B']
    if len(block_b) > 0 and 'time_bin' in block_b.columns:
        time_course_b = aggregate_by_time_bin(block_b)
        
        for cond in ['SS', 'NS']:
            cond_data = time_course_b[time_course_b['condition'] == cond]
            if len(cond_data) > 0:
                axes[1].plot(cond_data['time_bin']/1000, cond_data['mean'],
                           label=cond, linewidth=2)
                axes[1].fill_between(cond_data['time_bin']/1000,
                                   cond_data['mean'] - cond_data['ci95'],
                                   cond_data['mean'] + cond_data['ci95'],
                                   alpha=0.3)
        
        axes[1].set_xlabel('Time from Trial Onset (seconds)', fontsize=12)
        axes[1].set_ylabel(f'Pupil Size (baselined)', fontsize=12)
        axes[1].set_title('Block B: SS vs NS', fontsize=14, fontweight='bold')
        axes[1].legend(title='Condition')
        axes[1].axhline(y=0, color='gray', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"  Saved time course plot to {save_path}")
    
    plt.show()
    return fig

def plot_condition_comparison(df, save_path=None):
    """Plot boxplots comparing conditions."""
    pupil_col = 'pupil_corrected' if 'pupil_corrected' in df.columns else 'pupil_baselined'
    if pupil_col not in df.columns:
        pupil_col = 'CURRENT_FIX_PUPIL'
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # Block A
    block_a = df[df['block'] == 'A']
    if len(block_a) > 0:
        # Aggregate to trial level first
        trial_a = block_a.groupby(['participant', 'TRIAL_INDEX', 'condition'])[pupil_col].mean().reset_index()
        
        sns.boxplot(data=trial_a, x='condition', y=pupil_col, ax=axes[0], order=['BS', 'BN'])
        sns.stripplot(data=trial_a, x='condition', y=pupil_col, ax=axes[0], 
                     order=['BS', 'BN'], color='black', alpha=0.5, size=4)
        
        axes[0].set_xlabel('Condition', fontsize=12)
        axes[0].set_ylabel('Mean Pupil Size (baselined)', fontsize=12)
        axes[0].set_title('Block A: BS vs BN\n(Trial-level means)', fontsize=14, fontweight='bold')
    
    # Block B
    block_b = df[df['block'] == 'B']
    if len(block_b) > 0:
        trial_b = block_b.groupby(['participant', 'TRIAL_INDEX', 'condition'])[pupil_col].mean().reset_index()
        
        sns.boxplot(data=trial_b, x='condition', y=pupil_col, ax=axes[1], order=['SS', 'NS'])
        sns.stripplot(data=trial_b, x='condition', y=pupil_col, ax=axes[1],
                     order=['SS', 'NS'], color='black', alpha=0.5, size=4)
        
        axes[1].set_xlabel('Condition', fontsize=12)
        axes[1].set_ylabel('Mean Pupil Size (baselined)', fontsize=12)
        axes[1].set_title('Block B: SS vs NS\n(Trial-level means)', fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"  Saved comparison plot to {save_path}")
    
    plt.show()
    return fig

def plot_preprocessing_summary(df_original, df_cleaned, save_path=None):
    """Plot summary of preprocessing steps."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    
    pupil_col = 'CURRENT_FIX_PUPIL'
    
    # 1. Original vs Cleaned distribution
    if pupil_col in df_original.columns:
        axes[0, 0].hist(pd.to_numeric(df_original[pupil_col], errors='coerce').dropna(), 
                       bins=50, alpha=0.5, label='Original', color='red')
    if pupil_col in df_cleaned.columns:
        axes[0, 0].hist(df_cleaned[pupil_col].dropna(), 
                       bins=50, alpha=0.5, label='After Artifact Removal', color='blue')
    axes[0, 0].set_xlabel('Pupil Size')
    axes[0, 0].set_ylabel('Count')
    axes[0, 0].set_title('Pupil Size Distribution: Before vs After Cleaning')
    axes[0, 0].legend()
    
    # 2. Baseline distribution by condition
    if 'baseline_pupil' in df_cleaned.columns:
        for cond in df_cleaned['condition'].unique():
            baseline_data = df_cleaned[df_cleaned['condition'] == cond]['baseline_pupil'].dropna()
            if len(baseline_data) > 0:
                axes[0, 1].hist(baseline_data, bins=20, alpha=0.5, label=cond)
        axes[0, 1].set_xlabel('Baseline Pupil Size')
        axes[0, 1].set_ylabel('Count')
        axes[0, 1].set_title('Baseline Distribution by Condition')
        axes[0, 1].legend()
    
    # 3. Gaze position effect
    if 'CURRENT_FIX_Y' in df_cleaned.columns and 'pupil_baselined' in df_cleaned.columns:
        sample = df_cleaned.sample(min(1000, len(df_cleaned)))
        axes[1, 0].scatter(sample['CURRENT_FIX_Y'], sample['pupil_baselined'], 
                          alpha=0.3, s=5)
        axes[1, 0].set_xlabel('Y Gaze Position')
        axes[1, 0].set_ylabel('Baselined Pupil Size')
        axes[1, 0].set_title('Pupil Size vs Gaze Position (Y)')
    
    # 4. Before vs After gaze correction
    if 'pupil_baselined' in df_cleaned.columns and 'pupil_corrected' in df_cleaned.columns:
        sample = df_cleaned.sample(min(1000, len(df_cleaned)))
        axes[1, 1].scatter(sample['pupil_baselined'], sample['pupil_corrected'], 
                          alpha=0.3, s=5)
        axes[1, 1].plot([sample['pupil_baselined'].min(), sample['pupil_baselined'].max()],
                       [sample['pupil_baselined'].min(), sample['pupil_baselined'].max()],
                       'r--', label='Identity line')
        axes[1, 1].set_xlabel('Baselined Pupil Size')
        axes[1, 1].set_ylabel('Gaze-Corrected Pupil Size')
        axes[1, 1].set_title('Effect of Gaze Position Correction')
        axes[1, 1].legend()
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"  Saved preprocessing summary to {save_path}")
    
    plt.show()
    return fig

# =============================================================================
# MAIN ANALYSIS PIPELINE
# =============================================================================

def run_full_analysis():
    """Run the complete pupillometry analysis pipeline."""
    print("=" * 70)
    print("PUPILLOMETRY ANALYSIS")
    print("Following van Rij et al. (2019) Methodology")
    print("=" * 70)
    
    # Step 1: Load data
    print("\n1. LOADING DATA")
    print("-" * 40)
    df = load_all_fixation_data()
    
    if df is None or len(df) == 0:
        print("ERROR: No data loaded. Please check file paths.")
        return None
    
    df_original = df.copy()
    
    # Step 2: Artifact removal
    print("\n2. ARTIFACT REMOVAL")
    print("-" * 40)
    df = remove_artifacts(df)
    
    # Step 3: Baseline calculation
    print("\n3. BASELINE CALCULATION")
    print("-" * 40)
    df = calculate_baseline(df)
    
    # Step 4: Baseline correction
    print("\n4. BASELINE CORRECTION")
    print("-" * 40)
    df = apply_baseline_correction(df)
    
    # Step 5: Gaze position correction
    print("\n5. GAZE POSITION CORRECTION")
    print("-" * 40)
    df = apply_gaze_correction(df)
    
    # Step 5b: Outlier removal — minimal (4 SD) for P03 only; no removal for others. SS/NS unchanged.
    print("\n5b. OUTLIER REMOVAL (Per-Participant)")
    print("-" * 40)
    # Only P03: 4 SD (minimal). Others: no removal (use very high SD so nothing removed).
    df = remove_pupil_outliers(df, sd_threshold=999.0, participant_sd_thresholds={3: 4.0})
    
    # Step 6: Create time bins
    print("\n6. TIME BINNING")
    print("-" * 40)
    df = create_time_bins(df)
    
    # Step 7: Statistical analysis
    print("\n7. STATISTICAL ANALYSIS")
    print("-" * 40)
    stats_results = run_statistical_tests(df)
    
    for block, results in stats_results.items():
        print(f"\n{block}:")
        if 'BS_mean' in results:
            print(f"  BS: M = {results['BS_mean']:.2f}, SD = {results['BS_sd']:.2f}, n = {results['BS_n']}")
            print(f"  BN: M = {results['BN_mean']:.2f}, SD = {results['BN_sd']:.2f}, n = {results['BN_n']}")
        if 'SS_mean' in results:
            print(f"  SS: M = {results['SS_mean']:.2f}, SD = {results['SS_sd']:.2f}, n = {results['SS_n']}")
            print(f"  NS: M = {results['NS_mean']:.2f}, SD = {results['NS_sd']:.2f}, n = {results['NS_n']}")
        print(f"  t({results['df']}) = {results['t_statistic']:.3f}, p = {results['p_value']:.4f}, d = {results['cohens_d']:.3f}")
    
    # Step 8: Visualization
    print("\n8. VISUALIZATION")
    print("-" * 40)
    
    # Plot preprocessing summary
    print("  Creating preprocessing summary plot...")
    plot_preprocessing_summary(df_original, df, 
                              save_path=BASE_DIR / "pupillometry_preprocessing.png")
    
    # Plot time course
    print("  Creating time course plot...")
    plot_time_course(df, save_path=BASE_DIR / "pupillometry_time_course.png")
    
    # Plot condition comparison
    print("  Creating condition comparison plot...")
    plot_condition_comparison(df, save_path=BASE_DIR / "pupillometry_condition_comparison.png")
    
    # Save processed data
    print("\n9. SAVING PROCESSED DATA")
    print("-" * 40)
    df.to_csv(BASE_DIR / "pupillometry_processed_data.csv", index=False)
    print(f"  Saved processed data to pupillometry_processed_data.csv")
    
    # Save trial-level aggregated data
    trial_data = aggregate_by_trial(df)
    trial_data.to_csv(BASE_DIR / "pupillometry_trial_level.csv", index=False)
    print(f"  Saved trial-level data to pupillometry_trial_level.csv")
    
    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)
    
    return df, stats_results

# =============================================================================
# RUN ANALYSIS
# =============================================================================

if __name__ == "__main__":
    results = run_full_analysis()
