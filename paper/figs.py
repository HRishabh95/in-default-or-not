"""Figures (figs/*.pdf, vector, embedded TrueType) and data-driven LaTeX tables (tables/*.tex) for the data note.

Reads only data/interim/late_flags/outcome/FINAL.json and the final_* tables written by src/late_flags/final.py.
Drawn at printed size (text width 6.4 in), minimum 8 pt.
Usage: python reports/late_flags/paper/figs.py
"""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "data/interim/late_flags/outcome"
D = Path(__file__).resolve().parent
FIG, TAB = D / "figs", D / "tables"
FIG.mkdir(exist_ok=True)
TAB.mkdir(exist_ok=True)
F = json.loads((O / "FINAL.json").read_text())

W = 6.4
INK, MUTED, GRID = "#1F2937", "#4B5563", "#E5E7EB"
ACC, ACC2, GREY = "#1D4ED8", "#C2410C", "#9CA3AF"
BASE = {"font.family": "Palatino", "font.size": 9, "axes.titlesize": 9.5, "axes.labelsize": 9,
        "xtick.labelsize": 8.5, "ytick.labelsize": 8.5, "legend.fontsize": 8.5,
        "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
        "text.color": INK, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
        "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True, "axes.linewidth": 0.7,
        "xtick.major.width": 0.6, "ytick.major.width": 0.6, "legend.frameon": False,
        "pdf.fonttype": 42, "ps.fonttype": 42, "savefig.dpi": 600}


def _register_fonts():
    """Palatino on macOS is a .ttc collection; its faces are extracted to a local, uncommitted cache."""
    ttc = Path("/System/Library/Fonts/Palatino.ttc")
    if not ttc.exists():
        BASE["font.family"] = "DejaVu Serif"
        return
    from matplotlib import font_manager as fm
    from fontTools.ttLib import TTCollection
    cache = D / ".fonts"
    cache.mkdir(exist_ok=True)
    for i, font in enumerate(TTCollection(str(ttc)).fonts):
        out = cache / f"palatino_{i}.ttf"
        if not out.exists():
            font.save(str(out))
        fm.fontManager.addfont(str(out))


_register_fonts()
plt.rcParams.update(BASE)


def save(fig, name):
    fig.savefig(FIG / f"{name}.pdf")
    plt.close(fig)


def pct(x, d=1):
    return f"{100 * x:.{d}f}\\%"


def num(x):
    return f"{int(x):,}"


# ------------------------------------------------------------------ Figure 1: same bond, same date, across families
def fig_cross():
    c = pd.read_csv(O / "final_cross_family_cells.csv")
    e = c[(c.nfam >= 2) & (c.LOAN_CLASS == "BOND")].copy()
    e["fy"] = (e.y + 0.5 * e.m) / e.nfam  # share of families answering "in default" (a mixed family counts half)
    ex = F["cross_family"]["example"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(W, 2.5), gridspec_kw={"width_ratios": [1.35, 1]})
    bins = np.linspace(0, 1, 21)
    split = e[e.CLASS == "A"]
    rest = e[e.CLASS != "A"]
    a.hist([rest.fy, split.fy], bins=bins, stacked=True, color=[GREY, ACC], edgecolor="white", lw=1.0,
           label=[f"No opposite answers ({len(rest)})", f"Families give opposite answers ({len(split)})"])
    a.set_xticks([0, 0.25, 0.5, 0.75, 1])
    a.set_xticklabels(["0", "25", "50", "75", "100"])
    a.set_xlabel("Families reporting the bond in default (%)")
    a.set_ylabel("Bond-dates")
    a.set_title(f"(a) {len(e)} bond-dates held by \u22652 families", loc="left")
    a.legend(loc="upper left", fontsize=8, frameon=False)
    labs = ["In default", "Not in default"]
    fam = [ex["default"]["families"], ex["not_default"]["families"]]
    b.barh([1, 0], fam, color=[GREY, ACC], height=0.55, edgecolor="white")
    for y, k in [(1, "default"), (0, "not_default")]:
        r = ex[k]
        b.text(r["families"] + 0.6, y, f"{r['families']} families, {r['funds']} funds\nmedian price {r['median_price']:.1f}",
               va="center", fontsize=8)
    b.set_yticks([1, 0])
    b.set_yticklabels(labs)
    b.set_xlim(0, 75)
    b.set_xticks([0, 10, 20, 30])
    b.set_ylim(-0.6, 1.6)
    b.set_xlabel("Fund families")
    b.set_title("(b) Frontier 8% notes due 2027,\n      30 June 2020", loc="left")
    b.grid(False)
    fig.subplots_adjust(left=0.08, right=0.99, bottom=0.2, top=0.86, wspace=0.42)
    save(fig, "fig1_cross")


# ------------------------------------------------------------------ Figure 5: estimate by stage (research record)
def fig_stages():
    st = F["stages"]
    rows = [("Frozen confirmation run", st["FROZEN"], "pre-registered; 60 cases"),
            ("Debtor audit (Amendment 2)", st["AUDITED"], "post hoc; 57 cases"),
            ("Analysis sample (pooled)", st["FINAL"], "post hoc; less one DIP roll-up")]
    fig, a = plt.subplots(figsize=(W * 0.85, 1.6))
    for i, (lab, r, sub) in enumerate(rows):
        y = len(rows) - 1 - i
        col = GREY if i == 0 else ACC
        a.plot([100 * r["lo"], 100 * r["hi"]], [y, y], color=col, lw=2.2, solid_capstyle="round")
        a.plot(100 * r["share"], y, "o", color=col, ms=7, mec="white", mew=1.2, zorder=3)
        a.text(100 * r["hi"] + 1.2, y, f"{100 * r['share']:.1f}%  [{100 * r['lo']:.1f}, {100 * r['hi']:.1f}]",
               va="center", fontsize=9)
        a.text(-1.5, y + 0.13, lab, ha="right", va="center", fontsize=9, weight="bold")
        a.text(-1.5, y - 0.2, sub, ha="right", va="center", fontsize=8, color=MUTED)
    a.set_yticks([])
    a.set_xlim(0, 60)
    a.set_ylim(-0.6, 2.6)
    a.set_xlabel("Share not in default (%); 95% case-bootstrap CI")
    a.spines["left"].set_visible(False)
    fig.subplots_adjust(left=0.36, right=0.97, bottom=0.25, top=0.97)
    save(fig, "fig5_stages")


# ------------------------------------------------------------------ Figure 2: distribution across cases and families
def fig_distribution():
    c = pd.read_csv(O / "final_by_case.csv")
    f = pd.read_csv(O / "final_by_family.csv")
    f = f[f.units >= 10]
    fig, (a, b) = plt.subplots(1, 2, figsize=(W, 2.6), gridspec_kw={"width_ratios": [1.45, 1]})
    c = c.sort_values("share").reset_index(drop=True)
    a.scatter(np.arange(len(c)), 100 * c.share, s=8 + 0.35 * c.units, color=ACC, alpha=0.75, lw=0.6,
              edgecolor="white", zorder=3)
    a.axhline(100 * F["stages"]["FINAL"]["share"], color=MUTED, lw=0.8, ls="--")
    a.text(1, 100 * F["stages"]["FINAL"]["share"] + 3, f"all holdings {100 * F['stages']['FINAL']['share']:.1f}%",
           fontsize=8, color=MUTED)
    a.set_xticks([])
    a.set_xlabel(f"{len(c)} bankruptcy cases, ordered (marker size: holdings)")
    a.set_ylabel("Reported “not in default” (%)")
    a.set_ylim(-4, 104)
    a.set_title("(a) By issuer case", loc="left")
    bins = np.arange(0, 1.05, 0.1)
    b.hist(f.share, bins=bins, color=ACC, edgecolor="white", lw=1.2)
    b.set_xticks([0, 0.25, 0.5, 0.75, 1])
    b.set_xticklabels(["0", "25", "50", "75", "100"])
    b.set_xlabel("Reported “not in default” (%)")
    b.set_ylabel("Fund families")
    b.set_title(f"(b) {len(f)} fund families, \u226510 holdings", loc="left")
    fig.subplots_adjust(left=0.09, right=0.99, bottom=0.2, top=0.9, wspace=0.28)
    save(fig, "fig2_distribution")


# ------------------------------------------------------------------ Figure 3: what happened next
def fig_persistence():
    p = F["persistence"]
    parts = [("Flagged at a later report", p["FLAGGED_LATER"], ACC2),
             ("Still unflagged at ≥1 later report", p["window_ended_unflagged_ge1_later"], ACC),
             ("No later report before the window ended", p["window_ended_no_later_report"], GREY),
             ("Position gone (sold, exchanged, fund stopped filing)",
              p["EXITED_OR_UNLINKED_EXCHANGE"] + p["EXCHANGED_LINKED"] + p["FUND_GONE"], "#D1D5DB")]
    tot = p["total"]
    fig, a = plt.subplots(figsize=(W, 1.75))
    left = 0
    for lab, v, col in parts:
        a.barh(0, v, left=left, color=col, edgecolor="white", lw=2, height=0.55)
        a.text(left + v / 2, 0, f"{v:,}", ha="center", va="center", fontsize=9,
               color="white" if col in (ACC, ACC2) else INK, weight="bold")
        left += v
    a.set_xlim(0, tot)
    a.set_ylim(-0.9, 0.5)
    a.set_yticks([])
    a.set_xlabel(f"{tot:,} holdings reported “not in default” at the first post-petition report")
    a.grid(False)
    a.spines["left"].set_visible(False)
    hs = [plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in parts]
    a.legend(hs, [l for l, _, _ in parts], ncol=2, loc="lower left", bbox_to_anchor=(0, -0.05), fontsize=8,
             handlelength=1, columnspacing=1.2)
    fig.subplots_adjust(left=0.02, right=0.98, bottom=0.3, top=0.98)
    save(fig, "fig3_persistence")


# ------------------------------------------------------------------ Figure 4: prices in split cells
def fig_prices():
    p = pd.read_csv(O / "final_split_cell_prices.csv")
    fig, a = plt.subplots(figsize=(W * 0.55, W * 0.5))
    a.plot([0, 110], [0, 110], color=MUTED, lw=0.8, ls="--")
    a.scatter(p.FLAGGED, p.UNFLAGGED, s=12, color=ACC, alpha=0.6, edgecolor="white", lw=0.4, rasterized=True)
    a.set_xlim(0, 110)
    a.set_ylim(0, 110)
    a.set_xlabel("Median price, holders flagging default")
    a.set_ylabel("Median price, holders not flagging")
    a.set_aspect("equal")
    fig.subplots_adjust(left=0.17, right=0.97, bottom=0.15, top=0.97)
    save(fig, "fig4_prices")


# ------------------------------------------------------------------ tables
def tables():
    fc = F["final_counts"]
    st = F["stages"]
    rb = F["robustness"]
    # Table: estimates
    fin = st["FINAL"]
    B, L, K = F["by_asset"]["BOND"], F["by_asset"]["LOAN"], rb["known_end_date_only"]
    rows = [
        ("Bonds (main estimate)", B["share"], B["lo"], B["hi"], B["n_units"], B["n_cases"]),
        ("Prepetition loans (exploratory)", L["share"], L["lo"], L["hi"], L["n_units"], L["n_cases"]),
        ("Pooled: holding-weighted", fin["share"], fin["lo"], fin["hi"], fin["n_units"], fin["n_cases"]),
        ("\\quad case-weighted", fin["case_weighted"]["share"], fin["case_weighted"]["lo"], fin["case_weighted"]["hi"],
         fin["n_units"], fin["n_cases"]),
        ("\\quad value-weighted", fin["value_weighted"]["share"], fin["value_weighted"]["lo"],
         fin["value_weighted"]["hi"], fin["n_units"], fin["n_cases"]),
        ("\\quad cases with an identified effective date", K["share"], K["lo"], K["hi"], K["n_units"], K["n_cases"]),
        ("Record: debtor audit, pooled (post hoc)", st["AUDITED"]["share"], st["AUDITED"]["lo"], st["AUDITED"]["hi"],
         st["AUDITED"]["n_units"], st["AUDITED"]["n_cases"]),
        ("Record: frozen confirmation run, pooled (pre-registered)", st["FROZEN"]["share"], st["FROZEN"]["lo"],
         st["FROZEN"]["hi"], st["FROZEN"]["n_units"], st["FROZEN"]["n_cases"]),
    ]
    with open(TAB / "estimates.tex", "w") as t:
        for lab, s, lo, hi, n, c in rows:
            t.write(f"{lab} & {pct(s)} & [{100 * lo:.1f}, {100 * hi:.1f}] & {num(n)} & {c} \\\\\n")
    # Table: sample flow
    rm = pd.DataFrame(F["removed_by_audit"])
    flow = [("8-Ks with Item 1.03 mentioning Chapter 11 or 7 (2019 to 2026), grouped into cases", "380", ""),
            ("Petition verified from the 8-K text, with a petition date", "312", ""),
            ("Cases linked to prepetition corporate debt held by registered funds", "80", ""),
            ("Confirmation cases with a first post-petition report (frozen sample)", "60", "4,692"),
            ("\\quad less: securities of other companies (e.g.\\ Gates Global in Frontier)", "",
             num(rm[rm.LABEL == 'NOT_DEBTOR_OTHER'].units.sum())),
            ("\\quad less: securities of non-filing affiliates (e.g.\\ Ferrellgas, L.P.)", "",
             num(rm[rm.LABEL == 'NOT_DEBTOR_AFFILIATE'].units.sum())),
            ("\\quad less: security with unresolved debtor status", "", num(rm[rm.LABEL == 'UNCLEAR'].units.sum())),
            ("\\quad less: loan rolled up into the DIP facility (McDermott)", "", num(F["removed_rolled_up"]["units"])),
            ("Analysis sample", f"{fc['cases']}", num(fc["units"]))]
    with open(TAB / "flow.tex", "w") as t:
        for a, b, c in flow:
            t.write(f"{a} & {b} & {c} \\\\\n")
    cf = F["cross_family"]
    G = ("bonds", "loans", "all")
    with open(TAB / "cross_family.tex", "w") as t:
        for lab, k in [("Held by at least two fund families", "cells_ge2_families"),
                       ("\\quad (A) families give opposite answers", "cross_family_split"),
                       ("\\quad (B) every family reports in default", "all_families_Y"),
                       ("\\quad (C) every family reports not in default", "all_families_N"),
                       ("\\quad (D) no opposite answers; one family's own holdings disagree", "within_family_only")]:
            t.write(f"{lab} & " + " & ".join(f"{cf[g][k]:,}" for g in G) + " \\\\\n")
        t.write("Share in (A) & " + " & ".join(pct(cf[g]["split_share"]) for g in G) + " \\\\\n")
        t.write("\\quad 95\\% interval, clustered by case & " + " & ".join(
            f"{100 * cf[g]['split_ci'][0]:.1f} to {100 * cf[g]['split_ci'][1]:.1f}" for g in G) + " \\\\\n")
        t.write("\\quad weighting each case equally & " + " & ".join(pct(cf[g]["case_weighted"]) for g in G) + " \\\\\n")
        t.write("Cases represented / with (A) & " + " & ".join(f"{cf[g]['cases']} / {cf[g]['split_cases']}" for g in G)
                + " \\\\\n")
        t.write("\\midrule\n")
        t.write("Memo: with a family whose own holdings disagree (in A or D) & " + " & ".join(
            f"{cf[g]['cells_with_mixed_family']}" for g in G) + " \\\\\n")
    y = pd.read_csv(O / "final_by_year.csv")
    with open(TAB / "years.tex", "w") as t:
        for r in y.itertuples():
            t.write(f"{r.Y} & {r.cases} & {num(r.units)} & {pct(r.share)} \\\\\n")


if __name__ == "__main__":
    fig_cross()
    fig_stages()
    fig_distribution()
    fig_persistence()
    fig_prices()
    tables()
    print("figures and tables written")
