"""Write docs/reproduction.md from the outputs of ``reproduce_paper.py analyse``.

Usage: python tools/reproduction_report.py OUT_DEFAULT OUT_LEGACY [docs/reproduction.md]
(set STAGE1 to a description of the machine that ran stage 1, if it differs)

OUT_DEFAULT holds the run with the package's defaults (compared with the paper), OUT_LEGACY the run from a cache made
with ``prepare --legacy`` (compared with the first full-study draft, computed with the original scripts).
"""
import os
import platform
import subprocess
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


def fmt(e, lo, hi, p=None):
    m = "−"
    s = f"{e:.2f} [{lo:.2f}, {hi:.2f}]".replace("-", m)
    if p is not None and p == p:
        s += ", p < .001" if p < 0.001 else f", p = {p:.3f}".replace("0.", ".", 1)
    return s


def versions():
    import numpy, scipy, matplotlib
    import pupilread
    py = (f"Python {platform.python_version()}, pupilread {pupilread.__version__}, numpy {numpy.__version__}, "
          f"pandas {pd.__version__}, scipy {scipy.__version__}, matplotlib {matplotlib.__version__}")
    try:
        r = subprocess.run(["Rscript", "-e", "cat(R.version.string, '; lme4', as.character(packageVersion('lme4')), "
                            "'; mgcv', as.character(packageVersion('mgcv')), '; BLAS', sessionInfo()$BLAS)"],
                           capture_output=True, text=True)
        rv = r.stdout.strip()
    except OSError:
        rv = "R not found"
    return py, rv


def main(out_new, out_old, target, stage1=None):
    sys.path.insert(0, HERE)
    import reproduce_paper as rp
    tn, to = (pd.read_csv(os.path.join(d, "compare_tables.csv")) for d in (out_new, out_old))
    xn, xo = (pd.read_csv(os.path.join(d, "compare_text.csv")) for d in (out_new, out_old))
    oldout = os.path.join(out_old, "compare_old_outputs.csv")
    L = []
    w = L.append
    nt = int((tn["status"] == "match").sum())
    nx = int((xn["status"] == "match").sum())
    w("# Reproducing the paper with pupilread\n")
    no = int((to["status"] == "match").sum())
    xo_n = int((xo["status"] == "match").sum())
    w(f"With its defaults, pupilread reproduces {nt} of the {len(tn)} model estimates of Tables 3 and S1 (to the "
      f"printed digits, with the printed trial counts) and {nx} of the {len(xn)} numbers quoted in the text and "
      f"supplement. With `prepare --legacy`, it reproduces the first full-study draft, which the original scripts "
      f"computed: {no} of {len(to)} estimates and {xo_n} of {len(xo)} numbers, and every trial value and bin "
      "(last section).\n")
    w("Run on the 45 readers' Data Viewer reports (not included: participant data):\n")
    w("```\npython tools/reproduce_paper.py prepare --data \"Full study results\" --cache cache          # stage 1\n"
      "python tools/reproduce_paper.py analyse --cache cache --out reproduction --gamm --kcheck  # stage 2, needs R\n"
      "python tools/reproduce_paper.py prepare --data \"Full study results\" --cache cache_legacy --legacy\n"
      "python tools/reproduce_paper.py analyse --cache cache_legacy --out reproduction_legacy --gamm --old \"<old outputs>\"\n"
      "python tools/reproduction_report.py reproduction reproduction_legacy docs/reproduction.md\n```\n")
    w("## What changed between the draft and the paper\n")
    w("The original scripts made three assumptions that pupilread corrects (`CHANGELOG.md`): durations counted in "
      "samples assumed 1,000 Hz, although 6 of the 45 recordings were made at 2,000 Hz; blink padding summed blink flags "
      "in 8-bit integers, which overflow where blinks fill more than 127 of the 201 samples around a sample, so short "
      "gaps between blinks stayed valid; and one reader's reports listed every "
      "row twice. The repeated rows also doubled that reader's word counts in the companion study's screen for skimmed "
      "texts, so five of the reader's trials crossed its reading-rate ceiling; `reproduce_paper.py` recomputes the "
      "screen for that reader without the repeats (61 trials excluded as skimmed or incomplete, against 66). The paper "
      "reports the corrected values.\n")
    w("## Tables 3 and S1\n")
    w("| Table | Option | Paper (pupilread defaults) | Status | Draft (original scripts) | Legacy mode | Trials (paper, draft) |")
    w("| --- | --- | --- | --- | --- | --- | --- |")
    for _, r in tn.iterrows():
        o = to[(to["table"] == r["table"]) & (to["option"] == r["option"])]
        ref_old = (rp.ORIGINAL_TABLE3 if str(r["table"]) == "3" else rp.ORIGINAL_TABLE_S1).get(r["option"])
        draft = fmt(*ref_old) if ref_old else "not in the draft"
        leg = o["status"].iat[0] if len(o) else ("not run" if ref_old else "")
        ntr = rp.ORIGINAL_N_TRIALS.get(r["option"], rp.ORIGINAL_N_TRIALS["default"]) if ref_old else "–"
        w(f"| {r['table']} | {r['option']} | {fmt(r['estimate'], r['lo'], r['hi'], r['p'])} | {r['status']} | {draft} | "
          f"{leg} | {int(r['n'])}, {ntr} |")
    w("")
    w("## Numbers in the text\n")
    w("| Number | Paper | pupilread | Status | Draft | Legacy mode |")
    w("| --- | --- | --- | --- | --- | --- |")
    for _, r in xn.iterrows():
        o = xo[xo["number"] == r["number"]]
        dv = o["paper"].iat[0] if len(o) else ""
        ds = o["status"].iat[0] if len(o) else ""
        w(f"| {r['number']} | {r['paper']} | {r['package']} | {r['status']} | {dv} | {ds} |")
    w("")
    if os.path.exists(oldout):
        C = pd.read_csv(oldout)
        w("## Legacy mode against the outputs of the original scripts\n")
        w("Largest absolute difference between the package in legacy mode and the files the original scripts wrote "
          "(trial values in % of the reader mean, bins in arbitrary units or pixels):\n")
        w("| Quantity | Compared | Missing in one | Largest difference |")
        w("| --- | --- | --- | --- |")
        for _, r in C.iterrows():
            md = "" if pd.isna(r["max_abs_diff"]) else f"{r['max_abs_diff']:.2g}"
            w(f"| {r['quantity']} | {int(r['compared'])} | {int(r['missing_in_one'])} | {md} |")
        w("")
    py, rv = versions()
    w("## Software\n")
    w(f"Stage 2: {py}. {rv}.\n")
    if stage1:
        w(f"Stage 1: {stage1}.\n")
    with open(target, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"wrote {target}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 2:
        sys.exit(__doc__)
    main(a[0], a[1], a[2] if len(a) > 2 else os.path.join(HERE, os.pardir, "docs", "reproduction.md"),
         os.environ.get("STAGE1"))
