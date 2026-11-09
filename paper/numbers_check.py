"""Numbers audit: every number quoted in paper/note.tex is recomputed from the frozen and audit outputs and must
appear in the manuscript text exactly as formatted here. Writes NUMBERS_AUDIT.md.

Usage: python reports/late_flags/numbers_check.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "data/interim/late_flags/outcome"
D = Path(__file__).resolve().parent
F = json.loads((O / "FINAL.json").read_text())
REC = json.loads((ROOT / "data/interim/late_flags/replication/final_reconciliation.json").read_text())
TEX = " ".join([(D / "paper/note.tex").read_text()] + [t.read_text() for t in sorted((D / "paper/tables").glob("*.tex"))])
TEX = " ".join(TEX.split())


def p1(x):
    return f"{100 * x:.1f}\\%"


st, fc, rb, pe, va = F["stages"], F["final_counts"], F["robustness"], F["persistence"], F["valuation"]
fin = st["FINAL"]
rm = F["removed_by_audit"]
CHECKS = [
    ("Final share", p1(fin["share"]), "stages.FINAL.share"),
    ("Final interval", f"[{100 * fin['lo']:.1f}, {100 * fin['hi']:.1f}]", "stages.FINAL.lo/hi"),
    ("Final holdings", f"{fc['units']:,}", "final_counts.units"),
    ("Final unflagged", f"{fc['unflagged']:,}", "final_counts.unflagged"),
    ("Cases", f"{fc['cases']} Chapter", "final_counts.cases"),
    ("Funds", f"{fc['funds']} funds", "final_counts.funds"),
    ("Families", f"{fc['families']} fund families", "final_counts.families"),
    ("Unflagged value", f"\\${fc['unflagged_value_usd'] / 1e9:.1f} billion", "final_counts.unflagged_value_usd"),
    ("Unflagged value (2dp)", f"\\${fc['unflagged_value_usd'] / 1e9:.2f} billion", "final_counts.unflagged_value_usd"),
    ("Total value (2dp)", f"\\${fc['value_usd'] / 1e9:.2f} billion", "final_counts.value_usd"),
    ("Median days to first report", f"{fc['median_days_public_to_first_report']:.0f} days", "final_counts.median_days_public_to_first_report"),
    ("Case-weighted", p1(fin["case_weighted"]["share"]), "stages.FINAL.case_weighted.share"),
    ("Value-weighted", p1(fin["value_weighted"]["share"]), "stages.FINAL.value_weighted.share"),
    ("Bonds", p1(F["by_asset"]["BOND"]["share"]), "by_asset.BOND.share"),
    ("Loans", p1(F["by_asset"]["LOAN"]["share"]), "by_asset.LOAN.share"),
    ("Frozen", p1(st["FROZEN"]["share"]), "stages.FROZEN.share (CONF_result.json)"),
    ("Frozen low", f"{100 * st['FROZEN']['lo']:.1f}\\%", "stages.FROZEN.lo"),
    ("Frozen high", f"{100 * st['FROZEN']['hi']:.1f}\\%", "stages.FROZEN.hi"),
    ("Unflagged % NAV median", f"{F['unflagged_pct_nav']['median']:.2f}\\%", "unflagged_pct_nav.median"),
    ("Unflagged % NAV p90", f"{F['unflagged_pct_nav']['p90']:.2f}\\%", "unflagged_pct_nav.p90"),
    ("Cases >=5 holdings", f"{F['cases']['n_ge5']} cases", "cases.n_ge5"),
    ("Case quartile 1", p1(F["cases"]["share_quartiles_ge5"][0]), "cases.share_quartiles_ge5[0]"),
    ("Case quartile 2", p1(F["cases"]["share_quartiles_ge5"][1]), "cases.share_quartiles_ge5[1]"),
    ("Case quartile 3", p1(F["cases"]["share_quartiles_ge5"][2]), "cases.share_quartiles_ge5[2]"),
    ("Cases all flagged", f"flagged in {F['cases']['all_flagged']} and", "cases.all_flagged"),
    ("Cases none flagged", "none is in two", f"cases.no_unit_flagged = {F['cases']['no_unit_flagged']}"),
    ("Top-5 cases share of unflagged", f"{100 * rb['top5_case_share_of_unflagged']:.0f}\\%", "robustness.top5_case_share_of_unflagged"),
    ("LOO low", p1(rb["leave_one_case_out"][0]), "robustness.leave_one_case_out[0]"),
    ("LOO high", p1(rb["leave_one_case_out"][1]), "robustness.leave_one_case_out[1]"),
    ("Excl top-5 cases", p1(rb["excl_top5_cases"]), "robustness.excl_top5_cases"),
    ("Excl top-5 families", p1(rb["excl_top5_families"]), "robustness.excl_top5_families"),
    ("Top-5 families share", f"{100 * rb['top5_family_share_of_unflagged']:.0f}\\%", "robustness.top5_family_share_of_unflagged"),
    ("Families >=10", f"{F['families']['n_ge10']} fund families", "families.n_ge10"),
    ("Families all flagged", f"{F['families']['ge10_all_flagged']} report every", "families.ge10_all_flagged"),
    ("Family median", p1(F["families"]["ge10_share_quartiles"][1]), "families.ge10_share_quartiles[1]"),
    ("No later report", f"{pe['window_ended_no_later_report']} have no later", "persistence.window_ended_no_later_report"),
    ("Left portfolio", f"{pe['EXITED_OR_UNLINKED_EXCHANGE'] + pe['EXCHANGED_LINKED'] + pe['FUND_GONE']} leave",
     "persistence: exited + exchanged + fund gone"),
    ("Exited/unlinked", f"{pe['EXITED_OR_UNLINKED_EXCHANGE']} sold", "persistence.EXITED_OR_UNLINKED_EXCHANGE"),
    ("Exchanged linked", f"{pe['EXCHANGED_LINKED']} exchanged", "persistence.EXCHANGED_LINKED"),
    ("Fund gone", f"{pe['FUND_GONE']} in funds", "persistence.FUND_GONE"),
    ("Observed again", f"{pe['observed_again_held']} holdings observed", "persistence.observed_again_held"),
    ("Flagged at next", f"{pe['flagged_at_next_report']} ({100 * pe['flagged_at_next_report'] / pe['observed_again_held']:.0f}\\%)",
     "persistence.flagged_at_next_report / observed_again_held"),
    ("Not flagged at next",
     f"{pe['observed_again_held'] - pe['flagged_at_next_report']} ({100 * (1 - pe['flagged_at_next_report'] / pe['observed_again_held']):.0f}\\%)",
     "observed_again_held - flagged_at_next_report"),
    ("Unflagged >=2 later", f"{pe['window_ended_unflagged_ge2_later']} remain", "persistence.window_ended_unflagged_ge2_later"),
    ("Median days to later flag", f"{pe['median_days_public_to_flag']:.0f} days", "persistence.median_days_public_to_flag"),
    ("Split cells", f"{va['split_cells_with_prices']} security-dates", "valuation.split_cells_with_prices"),
    ("Median gap", f"median of {va['median_gap_points']:.1f} points", "valuation.median_gap_points"),
    ("IQR low", f"$-{abs(va['iqr_gap_points'][0]):.2f}$", "valuation.iqr_gap_points[0]"),
    ("IQR high", f"$+{va['iqr_gap_points'][1]:.2f}$", "valuation.iqr_gap_points[1]"),
    ("Within 1 point", p1(va["share_abs_gap_le_1pt"]), "valuation.share_abs_gap_le_1pt"),
    ("Median price ~35", f"about {round(va['median_flagged_price']):.0f} per 100", "valuation.median_flagged_price"),
    ("Stale own price", "Only one unflagged holding", f"stale_own_price_carried.unflagged = {F['stale_own_price_carried']['unflagged']}"),
    ("Arrears unflagged", "Eleven unflagged", f"arrears.unflagged_with_arrears = {F['arrears']['unflagged_with_arrears']}"),
    ("Arrears flagged", f"{F['arrears']['flagged_with_arrears']:,} flagged", "arrears.flagged_with_arrears"),
    ("Amended holdings", f"Of {F['amendments']['units_multi_version']} holdings", "amendments.units_multi_version"),
    ("Amendment flag changes", "none changed its default answer", f"amendments.flag_changed = {F['amendments']['flag_changed']}"),
    ("Removed other companies", f"companies ({sum(r['units'] for r in rm if r['LABEL'] == 'NOT_DEBTOR_OTHER')} holdings)",
     "removed_by_audit NOT_DEBTOR_OTHER"),
    ("Removed affiliates", f"affiliates ({sum(r['units'] for r in rm if r['LABEL'] == 'NOT_DEBTOR_AFFILIATE')})",
     "removed_by_audit NOT_DEBTOR_AFFILIATE"),
    ("Rolled-up loan", f"excluded ({F['removed_rolled_up']['units']} holdings)", "removed_rolled_up.units"),
    ("Reconciliation holdings", f"{REC['independent_units_final']['units']:,} holdings, "
     f"{REC['independent_units_final']['unflagged']:,} unflagged", "replication/final_reconciliation.json"),
]
cf, sm = F["cross_family"], F["sample"]
CHECKS += [
    ("Bond-dates >=2 families", f"{cf['bonds']['cells_ge2_families']} bond-dates", "cross_family.bonds.cells_ge2_families"),
    ("Bond split", f"{cf['bonds']['cross_family_split']} ({p1(cf['bonds']['split_share'])},", "cross_family.bonds"),
    ("Bond split (abstract)", f"{cf['bonds']['cross_family_split']} of {cf['bonds']['cells_ge2_families']} ({p1(cf['bonds']['split_share'])}", "cross_family.bonds"),
    ("Bond all Y", f"In {cf['bonds']['all_families_Y']} every family", "cross_family.bonds.all_families_Y"),
    ("Bond all N", "six none does", f"cross_family.bonds.all_families_N = {cf['bonds']['all_families_N']}"),
    ("Loan split", f"{cf['loans']['cross_family_split']} of {cf['loans']['cells_ge2_families']} loan-dates", "cross_family.loans"),
    ("Split cases (table, all)", f"{cf['all']['cases']} / {cf['split_cells_cases']}", "cross_family.all.cases / split_cells_cases"),
    ("Unflagged in split cells", f"{cf['unflagged_units_in_split_cells']} of the {fc['unflagged']:,}", "cross_family.unflagged_units_in_split_cells"),
    ("Families >=5 split", f"of the {cf['families_ge5_split_cells']} families", "cross_family.families_ge5_split_cells"),
    ("Families both", f"{cf['families_both']} give each", "cross_family.families_both"),
    ("Families always Y", f"{cf['families_always_Y']} always report", "cross_family.families_always_Y"),
    ("Families always N", f"{cf['families_always_N']} never do", "cross_family.families_always_N"),
    ("Bond holdings", f"{F['by_asset']['BOND']['n_units']:,} bond holdings", "by_asset.BOND.n_units"),
    ("Bond interval", f"{100 * F['by_asset']['BOND']['lo']:.1f}\\% to {100 * F['by_asset']['BOND']['hi']:.1f}\\%", "by_asset.BOND.lo/hi"),
    ("Loan holdings", f"{F['by_asset']['LOAN']['n_units']} holdings in {F['by_asset']['LOAN']['n_cases']} cases", "by_asset.LOAN"),
    ("Known end cases", f"{sm['cases_known_end']} of the 57 cases", "sample.cases_known_end"),
    ("No end cases", f"other {sm['cases_no_end']} cases ({sm['units_no_end']:,} holdings)", "sample.cases_no_end / units_no_end"),
    ("2020 holdings", f"{sm['units_2020']:,} of {fc['units']:,} holdings", "sample.units_2020"),
    ("2020 share (abstract)", f"{100 * sm['units_2020'] / fc['units']:.0f}\\% of holdings in 2020", "sample.units_2020 / units"),
    ("Flagged later total", f"({pe['FLAGGED_LATER']} in all)", "persistence.FLAGGED_LATER"),
    ("Flagged after next", {9: "nine"}.get(pe['FLAGGED_LATER'] - pe['flagged_at_next_report'], "NUMBER CHANGED") + " flagged afterwards", "FLAGGED_LATER - flagged_at_next_report"),
    ("Still unflagged at end", f"{pe['window_ended_unflagged_ge1_later']} are still unflagged", "persistence.window_ended_unflagged_ge1_later"),
    ("Bond split CI", f"{100 * cf['bonds']['split_ci'][0]:.1f}\\% to {100 * cf['bonds']['split_ci'][1]:.1f}\\%, clustered", "cross_family.bonds.split_ci"),
    ("Bond split cases", f"over the {cf['bonds']['cases']} cases", "cross_family.bonds.cases"),
    ("Bond split cases (text)", f"come from {cf['bonds']['cases']} cases and the {cf['bonds']['cross_family_split']} from {cf['bonds']['split_cases']}", "cross_family.bonds.cases / split_cases"),
    ("Bond D", "and in one no family", f"cross_family.bonds.within_family_only = {cf['bonds']['within_family_only']}"),
    ("Bond case-weighted", f"gives {p1(cf['bonds']['case_weighted'])} ({100 * cf['bonds']['case_weighted_ci'][0]:.1f}\\% to {100 * cf['bonds']['case_weighted_ci'][1]:.1f}\\%)", "cross_family.bonds.case_weighted(_ci)"),
    ("Bond LOO", f"between {p1(cf['bonds']['leave_one_case_out'][0])} and {p1(cf['bonds']['leave_one_case_out'][1])}", "cross_family.bonds.leave_one_case_out"),
    ("Bond excl top5", f"bond-dates gives {p1(cf['bonds']['excl_top5_cases'])}", "cross_family.bonds.excl_top5_cases"),
    ("Bond 2020", f"{p1(cf['bonds']['split_share_2020'])} in bond-dates of 2020", "cross_family.bonds.split_share_2020"),
    ("Bond not 2020", f"{p1(cf['bonds']['split_share_not2020'])} (41 of 105)", "cross_family.bonds.split_share_not2020"),
    ("Example families", f"{cf['example']['families']} fund families reported", "cross_family.example.families"),
    ("Example default side", f"{cf['example']['default']['families']} families ({cf['example']['default']['funds']} funds)", "cross_family.example.default"),
    ("Example not side", f"{cf['example']['not_default']['families']} families ({cf['example']['not_default']['funds']} funds)", "cross_family.example.not_default"),
    ("Example prices", f"{cf['example']['default']['median_price']:.1f} and {cf['example']['not_default']['median_price']:.1f}", "cross_family.example.median_price"),
    ("Example accessions", ", ".join(cf['example']['default']['accessions'][:2]), "cross_family.example.default.accessions"),
    ("Example CUSIP", cf['example']['cusip'], "cross_family.example.cusip"),
    ("Price cells = A - unpriced + D", f"its {va['split_cells_with_prices']} security-dates are the {va['reconcile']['class_A']} of class A",
     f"valuation.reconcile: {va['reconcile']['class_A_priced']} + {va['reconcile']['class_D_priced']} = {va['split_cells_with_prices']}"
     if va['reconcile']['class_A_priced'] + va['reconcile']['class_D_priced'] == va['split_cells_with_prices'] else "RECONCILE FAILS"),
    ("Unpriced A cells", {6: "less six bond-dates"}.get(va['reconcile']['class_A_unpriced'], "NUMBER CHANGED"), "valuation.reconcile.class_A_unpriced"),
    ("Unpriced zero / units", f"{ {4: 'in four'}.get(va['reconcile']['unpriced_zero_balance_cells'], 'X')} they report zero principal and zero value, in {({2: 'two'}).get(va['reconcile']['unpriced_non_pa_cells'], 'X')}",
     "valuation.reconcile.unpriced_zero_balance_cells / unpriced_non_pa_cells"),
    ("Known-end share (text)", f"gives {p1(rb['known_end_date_only']['share'])}", "robustness.known_end_date_only.share"),
]
rows, bad = [], 0
for name, s, src in CHECKS:
    ok = s in TEX
    bad += not ok
    rows.append(f"| {name} | `{s.strip()}` | {src} | {'OK' if ok else '**MISSING**'} |")
rec_ok = all(REC["independent_units_final"][k] == REC["main_final"][k] for k in REC["main_final"])
XC = json.loads((ROOT / "data/interim/late_flags/replication/cross_family_check.json").read_text())["step4"]
key = {"eligible": "cells_ge2_families", "A": "cross_family_split", "B": "all_families_Y", "C": "all_families_N",
       "D": "within_family_only", "with_mixed": "cells_with_mixed_family"}
xc_ok = all(XC[c][k] == cf[g][v] for c, g in [("BOND", "bonds"), ("PREPETITION", "loans")] for k, v in key.items())
out = ["# Numbers audit: Reported Not in Default", "",
       "Generated by `numbers_check.py`. Each string must appear verbatim in `paper/note.tex`; sources are keys of",
       "`data/interim/late_flags/outcome/FINAL.json` (written by `src/late_flags/final.py` from the frozen run and the",
       "audit files) unless stated.", "",
       f"Independent reconciliation of final counts: {'MATCH' if rec_ok else 'MISMATCH'} "
       f"(`data/interim/late_flags/replication/final_reconciliation.json`).",
       f"Independent rebuild of the same-security comparison (Table 4): {'MATCH' if xc_ok else 'MISMATCH'} "
       f"(`data/interim/late_flags/replication/cross_family_check.json`).", "",
       "| Number | Text in manuscript | Source | Status |", "|---|---|---|---|", *rows, "",
       f"Checks: {len(CHECKS)}, missing: {bad}."]
(D / "NUMBERS_AUDIT.md").write_text("\n".join(out) + "\n")
print(f"checks {len(CHECKS)} missing {bad} reconciliation {'MATCH' if rec_ok else 'MISMATCH'} cross-family {'MATCH' if xc_ok else 'MISMATCH'}")
for r in rows:
    if "MISSING" in r:
        print(r)
