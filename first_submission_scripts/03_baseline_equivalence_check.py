"""
Baseline Equivalence Check
Supplementary materials for: "Pupillometry for L2 reading research"
Corresponds to Section 3.3 (Baseline correction — verification step)

Tests whether raw baseline pupil sizes (first 500 ms of each trial)
differ systematically between conditions within each block, using
paired t-tests at the participant level (Mathôt & Vilotijević, 2023).
"""
import pandas as pd
from scipy import stats
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
trial_path = BASE_DIR / "pupillometry_trial_level.csv"

def main():
    t = pd.read_csv(trial_path)

    # Block A: BS vs BN (paired — same 5 participants)
    a = t[t["block"] == "A"]
    bs = a[a["condition"] == "BS"]["baseline_pupil_first"]
    bn = a[a["condition"] == "BN"]["baseline_pupil_first"]
    a_ppt = a.groupby(["participant", "condition"])["baseline_pupil_first"].mean().unstack(level=1)
    t_a, p_a = stats.ttest_rel(a_ppt["BS"], a_ppt["BN"])
    df_a = len(a_ppt) - 1

    # Block B: SS vs NS (paired — same 5 participants)
    b = t[t["block"] == "B"]
    ss = b[b["condition"] == "SS"]["baseline_pupil_first"]
    ns = b[b["condition"] == "NS"]["baseline_pupil_first"]
    b_ppt = b.groupby(["participant", "condition"])["baseline_pupil_first"].mean().unstack(level=1)
    t_b, p_b = stats.ttest_rel(b_ppt["SS"], b_ppt["NS"])
    df_b = len(b_ppt) - 1

    print("Baseline Pupil Size Check (raw, first 500 ms of trial, a.u.)")
    print("=" * 60)
    print("Block A:")
    print("  BS baseline: M = {:.2f} a.u., SD = {:.2f}".format(bs.mean(), bs.std()))
    print("  BN baseline: M = {:.2f} a.u., SD = {:.2f}".format(bn.mean(), bn.std()))
    print("  t({:d}) = {:.3f}, p = {:.4f}".format(df_a, t_a, p_a))
    print("")
    print("Block B:")
    print("  SS baseline: M = {:.2f} a.u., SD = {:.2f}".format(ss.mean(), ss.std()))
    print("  NS baseline: M = {:.2f} a.u., SD = {:.2f}".format(ns.mean(), ns.std()))
    print("  t({:d}) = {:.3f}, p = {:.4f}".format(df_b, t_b, p_b))
    print("")
    print("(Paired t-tests: same participants in both conditions per block.)")

if __name__ == "__main__":
    main()
