"""
Comprehension Accuracy
Supplementary materials for: "Pupillometry for L2 reading research"
Corresponds to Section 5.1 (Illustrative results)

Calculates comprehension question accuracy by block and condition
to verify participants operated within the productive range of
the inverted-U curve (Section 4.6).
"""
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
td = pd.read_csv(BASE_DIR / "combined_trial_data.csv", low_memory=False)
td["acc"] = pd.to_numeric(td["AnswerACC"], errors="coerce")
td["participant"] = td["participant"].astype(str)

# Block A: 5 participants 01, 02, 04, 05, 06
a = td[(td["block"] == "A") & (td["participant"].str.zfill(2).isin(["01", "02", "04", "05", "06"]))]
a["participant"] = a["participant"].str.zfill(2)
a = a[a["participant"].str.len() <= 2]

# Block B: extract base participant from 02, 02_b, 03_a, 03_b, 04_ss, 04_ns, 05_SS, 05_ns, 06_NS
b = td[(td["block"] == "B") & (td["block_b_condition"].isin(["ss", "ns"]))].copy()
def base_pid(x):
    s = str(x).lower()
    for p in ["02", "03", "04", "05", "06"]:
        if s.startswith(p):
            return p
    return None
b["pid"] = b["participant"].apply(base_pid)
b = b[b["pid"].isin(["02", "03", "04", "05", "06"])]

bs_c = a[a["condition"] == "BS"]["acc"].sum()
bs_n = len(a[a["condition"] == "BS"].dropna(subset=["acc"]))
bn_c = a[a["condition"] == "BN"]["acc"].sum()
bn_n = len(a[a["condition"] == "BN"].dropna(subset=["acc"]))
ss_c = b[b["block_b_condition"] == "ss"]["acc"].sum()
ss_n = len(b[b["block_b_condition"] == "ss"].dropna(subset=["acc"]))
ns_c = b[b["block_b_condition"] == "ns"]["acc"].sum()
ns_n = len(b[b["block_b_condition"] == "ns"].dropna(subset=["acc"]))

overall_c = bs_c + bn_c + ss_c + ns_c
overall_n = bs_n + bn_n + ss_n + ns_n

print("Comprehension accuracy (AnswerACC: 1=correct, 0=incorrect)")
print("Block A (simplified=BS, non-simplified=BN): BS {:.0f}/{} = {:.1f}%; BN {:.0f}/{} = {:.1f}%".format(bs_c, bs_n, 100*bs_c/bs_n, bn_c, bn_n, 100*bn_c/bn_n))
print("Block B (simplified-primed=SS, non-simplified-primed=NS): SS {:.0f}/{} = {:.1f}%; NS {:.0f}/{} = {:.1f}%".format(ss_c, ss_n, 100*ss_c/ss_n, ns_c, ns_n, 100*ns_c/ns_n))
print("Overall: {:.0f}/{} = {:.1f}%".format(overall_c, overall_n, 100*overall_c/overall_n))
