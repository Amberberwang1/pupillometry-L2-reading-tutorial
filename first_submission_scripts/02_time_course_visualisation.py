"""
Time Course Visualisation — Figure 3
Supplementary materials for: "Pupillometry for L2 reading research"
Corresponds to Section 3.5 (Data quality checks and visualisation)

Generates baseline-corrected pupil change over time by condition and block,
with Gaussian smoothing and 95% confidence intervals.
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from scipy.ndimage import gaussian_filter1d
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# Configuration: save next to this script so figures always update in your project folder
BASE_DIR = Path(__file__).resolve().parent
TIME_BIN_MS = 2000  # 2-second bins for better smoothing
MIN_FIXATIONS_PER_BIN = 20  # Minimum fixations required to include a bin
SMOOTH_SIGMA = 2  # Gaussian smoothing parameter

# Set style for publication-quality plots (Georgia, Word-style)
plt.rcParams.update({
    'font.family': 'Georgia',
    'font.size': 12,
    'axes.labelsize': 14,
    'axes.titlesize': 14,
    'legend.fontsize': 11,
    'xtick.labelsize': 11,
    'ytick.labelsize': 11,
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'axes.grid': True,
    'grid.alpha': 0.3,
    'grid.linestyle': '-',
    'lines.linewidth': 2.5
})

def load_and_prepare_data():
    """Load the processed data and calculate time from trial onset."""
    
    df = pd.read_csv(BASE_DIR / "pupillometry_processed_data.csv", low_memory=False)
    print(f"Loaded {len(df)} fixations")
    
    # Convert to numeric
    df['CURRENT_FIX_START'] = pd.to_numeric(df['CURRENT_FIX_START'], errors='coerce')
    df['pupil_baselined'] = pd.to_numeric(df['pupil_baselined'], errors='coerce')
    
    # Calculate time from trial start (per trial: Block B has separate SS/NS trials so include condition)
    group_cols = ['participant', 'TRIAL_INDEX', 'block', 'condition'] if 'block' in df.columns and 'condition' in df.columns else ['participant', 'TRIAL_INDEX']
    df['time_from_trial_start'] = df.groupby(group_cols)['CURRENT_FIX_START'].transform(
        lambda x: x - x.min()
    )
    
    # Convert to minutes
    df['time_minutes'] = df['time_from_trial_start'] / 60000
    
    # Remove any rows with missing pupil data
    df = df.dropna(subset=['pupil_baselined', 'time_from_trial_start'])
    
    print(f"After cleaning: {len(df)} fixations")
    print(f"Time range: 0 to {df['time_minutes'].max():.2f} minutes")
    
    return df

def find_reliable_time_range_per_block(df, min_fix=MIN_FIXATIONS_PER_BIN):
    """Find the time range where conditions within each block have sufficient data.
    
    Returns a dict with time ranges per block since Block A and B may have
    different time structures.
    """
    
    print("\nFinding reliable time range per block...")
    
    block_ranges = {}
    window_size = 0.1  # 6 seconds = 0.1 min
    
    for block in df['block'].unique():
        block_data = df[df['block'] == block]
        conditions = block_data['condition'].unique()
        
        # Find where BOTH conditions in this block have sufficient data
        # Check for start time (where data begins) and end time (where it becomes sparse)
        min_start = 0
        max_end = 2.0
        
        for cond in conditions:
            cond_data = block_data[block_data['condition'] == cond]
            
            # Find start: first window with enough data
            start_found = False
            for t in np.arange(0, 2.0, window_size):
                n_fix = len(cond_data[(cond_data['time_minutes'] >= t) & 
                                      (cond_data['time_minutes'] < t + window_size)])
                if n_fix >= min_fix:
                    if t > min_start:
                        min_start = t
                    start_found = True
                    break
            
            if not start_found:
                min_start = 0.5  # Default
            
            # Find end: where data becomes sparse
            for t in np.arange(min_start + 0.2, 2.0, window_size):
                n_fix = len(cond_data[(cond_data['time_minutes'] >= t) & 
                                      (cond_data['time_minutes'] < t + window_size)])
                if n_fix < min_fix:
                    if t < max_end:
                        max_end = t
                    break
        
        # Ensure reasonable range
        if max_end <= min_start:
            max_end = min_start + 0.5
        
        block_ranges[block] = {'start': round(min_start, 2), 'end': round(max_end, 2)}
        print(f"  Block {block}: {min_start:.2f} to {max_end:.2f} min")
    
    return block_ranges

def find_reliable_time_range(df, min_fix=MIN_FIXATIONS_PER_BIN):
    """Find global time range for compatibility. Uses per-block logic."""
    block_ranges = find_reliable_time_range_per_block(df, min_fix)
    
    # Use the most restrictive range across blocks
    max_end = min(r['end'] for r in block_ranges.values())
    max_end = max(0.5, max_end)
    
    print(f"\nUsing global time range: 0 to {max_end:.2f} minutes")
    return max_end

def create_binned_data(df, block_ranges, bin_size_ms=TIME_BIN_MS):
    """Create time-binned data with proper aggregation.
    
    Uses per-block time ranges since Block A and B may have different structures.
    Uses trial-level aggregation for robust estimates.
    
    Args:
        df: DataFrame with fixation data
        block_ranges: Dict with time ranges per block, e.g. {'A': {'start': 0, 'end': 1.2}, 'B': {'start': 0.5, 'end': 1.0}}
        bin_size_ms: Time bin size in milliseconds
    """
    
    all_stats = []
    bin_size_min = bin_size_ms / 60000
    
    for block in df['block'].unique():
        block_data = df[df['block'] == block].copy()
        
        # Get time range for this block
        if block in block_ranges:
            start_time = block_ranges[block]['start']
            end_time = block_ranges[block]['end']
        else:
            start_time = 0
            end_time = 1.0
        
        # Filter to reliable time range
        block_filtered = block_data[
            (block_data['time_minutes'] >= start_time) & 
            (block_data['time_minutes'] <= end_time)
        ].copy()
        
        if len(block_filtered) == 0:
            continue
        
        # Create time bins relative to start (round to avoid float bin-splitting)
        raw_bin = ((block_filtered['time_minutes'] - start_time) // bin_size_min) * bin_size_min
        block_filtered['time_bin'] = np.round(raw_bin, 4)
        
        # Step 1: Average within each trial and time bin
        trial_means = block_filtered.groupby(
            ['block', 'condition', 'participant', 'TRIAL_INDEX', 'time_bin']
        )['pupil_baselined'].mean().reset_index()
        
        # Step 2: Calculate condition-level statistics across trials
        condition_stats = trial_means.groupby(
            ['block', 'condition', 'time_bin']
        ).agg({
            'pupil_baselined': ['mean', 'std', 'count']
        }).reset_index()
        
        condition_stats.columns = ['block', 'condition', 'time_bin', 'mean', 'std', 'n']
        condition_stats['se'] = condition_stats['std'] / np.sqrt(condition_stats['n'])
        condition_stats['ci95'] = 1.96 * condition_stats['se']
        
        # Filter bins with too few trials (at least 3 trials per bin)
        condition_stats = condition_stats[condition_stats['n'] >= 3]
        
        all_stats.append(condition_stats)
    
    if all_stats:
        return pd.concat(all_stats, ignore_index=True)
    else:
        return pd.DataFrame()

def plot_van_rij_style(condition_stats, block_ranges, save_path):
    """
    Create van Rij et al. style plot with:
    - Solid vs dashed lines
    - Gray shading for CI
    - Clean publication style
    - Per-block time ranges
    """
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.patch.set_facecolor('white')
    
    # =========== BLOCK A ===========
    ax = axes[0]
    block_a = condition_stats[condition_stats['block'] == 'A']
    max_time_a = block_ranges.get('A', {}).get('end', 1.0) - block_ranges.get('A', {}).get('start', 0)
    
    for cond, ls in [('BS', '-'), ('BN', '--')]:
        data = block_a[block_a['condition'] == cond].sort_values('time_bin')
        if len(data) > 2:
            t = data['time_bin'].values
            m = data['mean'].values
            ci = data['ci95'].values
            
            # Apply smoothing
            if len(m) > 3:
                m_smooth = gaussian_filter1d(m, sigma=SMOOTH_SIGMA)
                ci_smooth = gaussian_filter1d(ci, sigma=SMOOTH_SIGMA)
            else:
                m_smooth, ci_smooth = m, ci
            
            # Plot CI band
            ax.fill_between(t, m_smooth - ci_smooth, m_smooth + ci_smooth,
                          color='gray', alpha=0.25)
            # Plot mean line
            ax.plot(t, m_smooth, color='black', linestyle=ls, linewidth=2.5, label=cond)
    
    ax.axhline(y=0, color='gray', linestyle='-', alpha=0.5, linewidth=0.8)
    ax.set_xlabel('Time from trial onset (min)', fontsize=14)
    ax.set_ylabel('Pupil change (a.u.)', fontsize=14)
    ax.set_title('Block A', fontsize=14, fontweight='bold',
                bbox=dict(boxstyle='round', facecolor='#e0e0e0', alpha=0.9))
    ax.legend(loc='upper right', framealpha=0.95)
    if len(block_a) > 0:
        ax.set_xlim(0, block_a['time_bin'].max() * 1.05)
    ax.grid(True, alpha=0.3)

    # Block B: shorter x-range reflects shorter trial duration (real data)
    ax = axes[1]
    block_b = condition_stats[condition_stats['block'] == 'B']

    for cond, ls in [('SS', '-'), ('NS', '--')]:
        data = block_b[block_b['condition'] == cond].sort_values('time_bin')
        if len(data) > 2:
            t = data['time_bin'].values
            m = data['mean'].values
            ci = data['ci95'].values
            
            if len(m) > 3:
                m_smooth = gaussian_filter1d(m, sigma=SMOOTH_SIGMA)
                ci_smooth = gaussian_filter1d(ci, sigma=SMOOTH_SIGMA)
            else:
                m_smooth, ci_smooth = m, ci
            
            ax.fill_between(t, m_smooth - ci_smooth, m_smooth + ci_smooth,
                          color='gray', alpha=0.25)
            ax.plot(t, m_smooth, color='black', linestyle=ls, linewidth=2.5, label=cond)
    
    ax.axhline(y=0, color='gray', linestyle='-', alpha=0.5, linewidth=0.8)
    ax.set_xlabel('Time from trial onset (min)', fontsize=14)
    ax.set_ylabel('Pupil change (a.u.)', fontsize=14)
    ax.set_title('Block B', fontsize=14, fontweight='bold',
                bbox=dict(boxstyle='round', facecolor='#e0e0e0', alpha=0.9))
    ax.legend(loc='upper right', framealpha=0.95)
    if len(block_b) > 0:
        ax.set_xlim(0, block_b['time_bin'].max() * 1.05)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    save_path = Path(save_path)
    plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close('all')
    print(f"Saved: {save_path.resolve()}")

def plot_color_version(condition_stats, block_ranges, save_path):
    """
    Create colored version with distinct colors per condition.
    """
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.patch.set_facecolor('white')
    
    colors = {'BS': '#1f77b4', 'BN': '#ff7f0e', 'SS': '#2ca02c', 'NS': '#d62728'}
    
    # =========== BLOCK A ===========
    ax = axes[0]
    block_a = condition_stats[condition_stats['block'] == 'A']
    
    for cond in ['BS', 'BN']:
        data = block_a[block_a['condition'] == cond].sort_values('time_bin')
        if len(data) > 2:
            t = data['time_bin'].values
            m = data['mean'].values
            ci = data['ci95'].values
            
            if len(m) > 3:
                m_smooth = gaussian_filter1d(m, sigma=SMOOTH_SIGMA)
                ci_smooth = gaussian_filter1d(ci, sigma=SMOOTH_SIGMA)
            else:
                m_smooth, ci_smooth = m, ci
            
            ax.fill_between(t, m_smooth - ci_smooth, m_smooth + ci_smooth,
                          color=colors[cond], alpha=0.2)
            ax.plot(t, m_smooth, color=colors[cond], linewidth=2.5, label=cond)
    
    ax.axhline(y=0, color='gray', linestyle='--', alpha=0.5, linewidth=1)
    ax.set_xlabel('Time from trial onset (min)', fontsize=14)
    ax.set_ylabel('Pupil change (a.u.)', fontsize=14)
    ax.set_title('Block A', fontsize=14, fontweight='bold',
                bbox=dict(boxstyle='round', facecolor='#e0e0e0', alpha=0.9))
    ax.legend(loc='upper right', framealpha=0.95)
    if len(block_a) > 0:
        ax.set_xlim(0, block_a['time_bin'].max() * 1.05)
    ax.grid(True, alpha=0.3)

    # =========== BLOCK B ===========
    ax = axes[1]
    block_b = condition_stats[condition_stats['block'] == 'B']
    
    for cond in ['SS', 'NS']:
        data = block_b[block_b['condition'] == cond].sort_values('time_bin')
        if len(data) > 2:
            t = data['time_bin'].values
            m = data['mean'].values
            ci = data['ci95'].values
            
            if len(m) > 3:
                m_smooth = gaussian_filter1d(m, sigma=SMOOTH_SIGMA)
                ci_smooth = gaussian_filter1d(ci, sigma=SMOOTH_SIGMA)
            else:
                m_smooth, ci_smooth = m, ci
            
            ax.fill_between(t, m_smooth - ci_smooth, m_smooth + ci_smooth,
                          color=colors[cond], alpha=0.2)
            ax.plot(t, m_smooth, color=colors[cond], linewidth=2.5, label=cond)
    
    ax.axhline(y=0, color='gray', linestyle='--', alpha=0.5, linewidth=1)
    ax.set_xlabel('Time from trial onset (min)', fontsize=14)
    ax.set_ylabel('Pupil change (a.u.)', fontsize=14)
    ax.set_title('Block B', fontsize=14, fontweight='bold',
                bbox=dict(boxstyle='round', facecolor='#e0e0e0', alpha=0.9))
    ax.legend(loc='upper right', framealpha=0.95)
    if len(block_b) > 0:
        ax.set_xlim(0, block_b['time_bin'].max() * 1.05)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    save_path = Path(save_path)
    plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close('all')
    print(f"Saved: {save_path.resolve()}")

def main():
    print("=" * 60)
    print("PUPILLOMETRY TIME COURSE - FIXED VERSION")
    print("Following van Rij et al. (2019) methodology")
    print("Block A: 5 participants (P1, P2, P4, P5, P6); Block B: 5 participants (P2–P6, SS & NS)")
    print("=" * 60)
    
    # Load data
    print("\n1. Loading data...")
    df = load_and_prepare_data()
    
    # Find reliable time range per block
    print("\n2. Finding reliable time range per block...")
    block_ranges = find_reliable_time_range_per_block(df)
    
    # Create binned data with per-block ranges
    print("\n3. Creating time-binned data...")
    condition_stats = create_binned_data(df, block_ranges)
    print(f"   {len(condition_stats)} data points for plotting")

    # Save binned means (no smoothing) for verification that the figure reflects real data
    verify_path = BASE_DIR / "pupillometry_timecourse_binned_means.csv"
    condition_stats.to_csv(verify_path, index=False)
    print(f"   Saved binned means to {verify_path.name} (for figure verification)")

    # Check what we have
    for block in condition_stats['block'].unique():
        block_data = condition_stats[condition_stats['block'] == block]
        print(f"   Block {block}: {len(block_data)} bins, conditions: {block_data['condition'].unique()}")
    
    # Generate plots
    print("\n4. Generating plots...")
    
    # Van Rij style (black/gray, solid vs dashed)
    plot_van_rij_style(condition_stats, block_ranges,
                      BASE_DIR / "pupillometry_time_course_vanrij_style.png")
    
    # Color version
    plot_color_version(condition_stats, block_ranges,
                      BASE_DIR / "pupillometry_time_course_CORRECTED.png")
    
    # Also save as the main time course file
    plot_van_rij_style(condition_stats, block_ranges,
                      BASE_DIR / "pupillometry_time_course.png")
    
    print("\n" + "=" * 60)
    print("DONE!")
    print("Generated plots:")
    print("  - pupillometry_time_course.png (van Rij style)")
    print("  - pupillometry_time_course_vanrij_style.png")
    print("  - pupillometry_time_course_CORRECTED.png (color version)")
    print("=" * 60)

if __name__ == "__main__":
    main()
