#!/usr/bin/env python3
"""Figures 2, 3 and S1 of the tutorial from the outputs of reproduce_paper.py (same layout as the published figures).

Usage: python tools/paper_figures.py <reproduction folder> [<output folder>] [--fonts <folder with LiberationSans-*.ttf>]
Reads first5s.csv, grand_mean.csv, events_return_sweep.csv, events_blink.csv (kept trials; events_blink_all_trials.csv
with --blinks all), for_R/gamm/gamm_diff.csv and the residual plots gamm.R writes (for_R/gamm/gamm_residuals_M*.png).
"""
import argparse
import glob
import logging
import os

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
K, BAND = "black", "#c8c8c8"
LAB = {"simplified": "Simplified (STE)", "non-simplified": "Non-simplified"}
LS = {"simplified": "-", "non-simplified": (0, (4, 2))}


def style(fonts=None):
    for f in glob.glob(os.path.join(fonts or "", "LiberationSans-*.ttf")):
        font_manager.fontManager.addfont(f)
    plt.rcParams.update({"font.family": ["Arial", "Liberation Sans", "DejaVu Sans"], "font.size": 8, "axes.linewidth": 0.6,
                         "axes.edgecolor": "black", "xtick.major.width": 0.6, "ytick.major.width": 0.6,
                         "xtick.major.size": 3, "ytick.major.size": 3, "xtick.direction": "out", "ytick.direction": "out",
                         "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
                         "svg.fonttype": "none", "axes.unicode_minus": True, "axes.labelsize": 8, "xtick.labelsize": 7.5,
                         "ytick.labelsize": 7.5, "lines.solid_capstyle": "butt"})


def panel(a, letter):
    a.text(-0.16, 1.06, letter, transform=a.transAxes, fontsize=10, fontweight="bold", va="bottom", ha="left")


def save(fig, out, name):
    fig.savefig(os.path.join(out, f"{name}.png"), dpi=600, bbox_inches="tight", facecolor="white")
    fig.savefig(os.path.join(out, f"{name}.svg"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def figure2(d, out, blinks="kept", base_end=200):
    c = pd.read_csv(os.path.join(d, "first5s.csv"))
    g = pd.read_csv(os.path.join(d, "grand_mean.csv"))
    rs = pd.read_csv(os.path.join(d, "events_return_sweep.csv"))
    bl = pd.read_csv(os.path.join(d, "events_blink.csv" if blinks == "kept" else "events_blink_all_trials.csv"))
    fig, ax = plt.subplots(2, 2, figsize=(6.6, 4.6))
    fig.subplots_adjust(wspace=0.38, hspace=0.62)
    a = ax[0, 0]
    x = (c["sec"] + 0.5) / 10
    a.axvspan(0, base_end / 1000, color="#ececec", lw=0, zorder=0)
    a.fill_between(x, c["mean"] - 1.96 * c["sem"], c["mean"] + 1.96 * c["sem"], color=BAND, lw=0)
    a.plot(x, c["mean"], color=K, lw=1.0)
    a.set_xlim(0, 5)
    a.set_xlabel("Time from text onset (s)")
    a.set_ylabel("Pupil size relative to\nreader mean (%)")
    a.set_title("Text onset", fontsize=8, loc="left")
    panel(a, "A")
    a = ax[0, 1]
    for v in ("simplified", "non-simplified"):
        s = g[g["level"] == v]
        xs = s["sec"] + 0.5
        a.fill_between(xs, s["mean"] - 1.96 * s["sem"], s["mean"] + 1.96 * s["sem"], color=BAND, alpha=0.45, lw=0)
        a.plot(xs, s["mean"], color=K, lw=1.0, ls=LS[v], label=LAB[v])
    a.axhline(0, color=K, lw=0.4)
    a.set_xlim(0, 40)
    a.set_xlabel("Time from text onset (s)")
    a.set_ylabel("Pupil change from baseline\n(% of reader mean)")
    a.legend(fontsize=7, loc="upper right", handlelength=2.6)
    a.set_title("Across the trial", fontsize=8, loc="left")
    panel(a, "B")
    a = ax[1, 0]
    rs = rs[rs["type"] == "return sweep"]
    for e, col, lab in (("left", K, "Left eye"), ("right", "#8a8a8a", "Right eye")):
        z = rs[rs["eye"] == e].sort_values("lag")
        xs = z["lag"] / 1000
        a.fill_between(xs, z["mean"] - 1.96 * z["sem"], z["mean"] + 1.96 * z["sem"], color=BAND, alpha=0.45, lw=0)
        a.plot(xs, z["mean"], color=col, lw=1.0, label=lab)
    a.axhline(0, color=K, lw=0.4)
    a.axvline(0, color=K, lw=0.4, ls=":")
    a.axvline(0.22, color=K, lw=0.4, ls=(0, (1, 2)))
    a.text(0.235, a.get_ylim()[1] * 0.97, "220 ms", fontsize=6.5, va="top")
    a.set_xlim(-0.3, 1.0)
    a.set_xlabel("Time from landing (s)")
    a.set_ylabel("Pupil change\n(% of reader mean)")
    a.legend(fontsize=7, loc="center right", handlelength=1.8)
    a.set_title("Return sweeps", fontsize=8, loc="left")
    panel(a, "C")
    a = ax[1, 1]
    for v in ("simplified", "non-simplified"):
        s = bl[(bl["version"] == v) & (bl["lag"] > 100)].sort_values("lag")   # after the padding
        a.plot(s["lag"] / 1000, s["pooled_pct"], color=K, lw=0.9, ls=LS[v], label=LAB[v])
    a.axhline(0, color=K, lw=0.4)
    a.axvline(0, color=K, lw=0.4, ls=":")
    a.set_xlabel("Time from blink offset (s)")
    a.set_ylabel("Pupil change\n(% of reader mean)")
    a.set_title("Blink offset", fontsize=8, loc="left")
    panel(a, "D")
    save(fig, out, "Figure2_pupil_signals")


def figure3(d, out):
    H = pd.read_csv(os.path.join(d, "for_R", "gamm", "gamm_diff.csv"))
    fig, b = plt.subplots(figsize=(4.6, 2.7))
    for m, ls, band in (("M1 no gaze term", "-", "#c8c8c8"), ("M2 gaze surface", (0, (4, 2)), "#e3e3e3")):
        z = H[H["model"] == m]
        b.fill_between(z["Time"], z["lo"], z["hi"], color=band, alpha=0.6, lw=0)
        b.plot(z["Time"], z["diff"], color=K, lw=1.0, ls=ls, label="No gaze term" if m.startswith("M1") else "Gaze surface")
    b.axhline(0, color=K, lw=0.5, ls=(0, (3, 2)))
    b.set_xlim(0, 20)
    b.set_xticks([0, 5, 10, 15, 20])
    b.set_xlabel("Time from text onset (s)")
    b.set_ylabel("Simplified minus\nnon-simplified (% of reader mean)")
    b.legend(fontsize=7, loc="upper left", handlelength=2.6, ncol=2)
    save(fig, out, "Figure3_gamm_difference")


def figure_s1(d, out, fonts=None):
    from PIL import Image, ImageDraw, ImageFont

    def font(name, size):
        for f in (os.path.join(fonts or "", name), os.path.join("/usr/share/fonts/truetype/liberation", name)):
            if os.path.exists(f):
                return ImageFont.truetype(f, size)
        return ImageFont.load_default()
    bold, reg = font("LiberationSans-Bold.ttf", 34), font("LiberationSans-Regular.ttf", 34)
    rows = [("M1", "Model without gaze term"), ("M2", "Model with gaze surface")]
    cols = ["autocorrelation function", "normal Q-Q plot"]
    panels = []
    for name, _ in rows:
        im = Image.open(os.path.join(d, "for_R", "gamm", f"gamm_residuals_{name}.png")).convert("RGB")
        w, h = im.size
        g = ImageDraw.Draw(im)
        g.rectangle((0, 0, w // 2 - 1, 30), fill="white")
        g.rectangle((w // 2 + 250, 0, w - 1, 66), fill="white")
        panels.append([im.crop((0, 20, w // 2, h)), im.crop((w // 2, 20, w, h))])
    pw, ph = panels[0][0].size
    head, gap, margin = 70, 40, 30
    fig = Image.new("RGB", (2 * pw + gap + 2 * margin, 2 * (head + ph) + gap + 2 * margin), "white")
    dr = ImageDraw.Draw(fig)
    letters = iter("ABCD")
    for r, (name, rlabel) in enumerate(rows):
        y0 = margin + r * (head + ph + gap)
        for c in range(2):
            x0 = margin + c * (pw + gap)
            fig.paste(panels[r][c], (x0, y0 + head))
            dr.text((x0, y0 + 14), next(letters), font=bold, fill="black")
            dr.text((x0 + 44, y0 + 14), f"{rlabel}: {cols[c]}", font=reg, fill="black")
    fig.save(os.path.join(out, "FigureS1_gamm_residuals.png"), dpi=(200, 200))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folder")
    p.add_argument("out", nargs="?")
    p.add_argument("--fonts")
    p.add_argument("--blinks", choices=["kept", "all"], default="kept")
    a = p.parse_args()
    out = a.out or os.path.join(a.folder, "figures")
    os.makedirs(out, exist_ok=True)
    style(a.fonts)
    figure2(a.folder, out, a.blinks)
    if os.path.exists(os.path.join(a.folder, "for_R", "gamm", "gamm_diff.csv")):
        figure3(a.folder, out)
    if os.path.exists(os.path.join(a.folder, "for_R", "gamm", "gamm_residuals_M2.png")):
        figure_s1(a.folder, out, a.fonts)
    print("figures written to", out)


if __name__ == "__main__":
    main()
