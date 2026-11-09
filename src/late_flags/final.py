"""Paper numbers: every figure in the data note comes from this file's output (outcome/FINAL.json, outcome/final_*).

Stages kept side by side:
  FROZEN   - pre-registered confirmation run (outcome/CONF_result.json), unchanged;
  AUDITED  - Amendment 2: debtor-issued CUSIPs, reports before emergence (outcome/CONF_amendment2.json);
  FINAL    - AUDITED minus the loan rolled up into the DIP (audit/loan_classes.csv), the analysis sample.
The frozen estimators and persistence rules from outcome.py are reused unchanged.

Usage: python src/late_flags/final.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from outcome import DRAWS, SEED, boot_case_weighted, boot_share, persistence

ROOT = Path(__file__).resolve().parents[2]
R = ROOT / "data/interim/late_flags"
O = R / "outcome"
PERSIST = ["FLAGGED_LATER", "WINDOW_ENDED_UNFLAGGED", "EXCHANGED_LINKED", "EXITED_OR_UNLINKED_EXCHANGE", "FUND_GONE"]


def final_sample():
    w = pd.read_parquet(O / "CONF_amendment2_units.parquet")
    loans = pd.read_csv(R / "audit/loan_classes.csv").set_index("CUSIP").LOAN_CLASS
    w["LOAN_CLASS"] = w.CUSIP.map(loans).fillna(pd.Series(np.where(w.ASSET_CAT == "LON", "UNREVIEWED_LOAN", "BOND"), index=w.index))
    aud = w[(w.RD_STATUS != "POST_EMERGENCE") & (w.LABEL == "DEBTOR")]
    return w, aud, aud[aud.LOAN_CLASS != "ROLLED_UP"].copy()


def valuation(s, obs):
    """Price comparison at the final sample's CUSIP x report-date cells, all holders with prices."""
    cells = s[["CUSIP", "RD"]].drop_duplicates()
    o = obs.merge(cells, on=["CUSIP", "RD"])
    o = o[o.F != "BLANK"].dropna(subset=["PRICE"])
    by = o.groupby(["CUSIP", "RD", "F"]).PRICE.median().unstack()
    both = by.dropna(subset=["FLAGGED", "UNFLAGGED"]) if {"FLAGGED", "UNFLAGGED"} <= set(by.columns) else by.iloc[:0]
    d = both.UNFLAGGED - both.FLAGGED
    both = both.reset_index()
    both.to_csv(O / "final_split_cell_prices.csv", index=False)
    return {"split_cells_with_prices": int(len(d)), "median_gap_points": float(d.median()),
            "iqr_gap_points": [float(d.quantile(.25)), float(d.quantile(.75))],
            "share_abs_gap_le_1pt": round(float((d.abs() <= 1).mean()), 4),
            "share_unflagged_higher_gt5": round(float((d > 5).mean()), 4),
            "share_unflagged_lower_lt_minus5": round(float((d < -5).mean()), 4),
            "median_flagged_price": float(both.FLAGGED.median()),
            "median_unflagged_price": float(both.UNFLAGGED.median())}


def cross_family(s, obs):
    """Same CUSIP, same report date, held by >= 2 fund families (post hoc, requested in review). A family's answer
    is Y if all its holdings say Y, N if all say N, MIXED otherwise."""
    cells = s[["CUSIP", "RD", "LOAN_CLASS"]].drop_duplicates(["CUSIP", "RD"])
    x = obs.merge(cells, on=["CUSIP", "RD"])
    x = x[x.F != "BLANK"]
    fam = x.groupby(["CUSIP", "RD", "FAMILY"]).F.agg(
        lambda f: "Y" if (f == "FLAGGED").all() else ("N" if (f == "UNFLAGGED").all() else "MIXED")).rename("FF").reset_index()
    fam = fam.merge(cells, on=["CUSIP", "RD"])
    c = fam.groupby(["CUSIP", "RD", "LOAN_CLASS"]).FF.agg(
        nfam="size", y=lambda f: int((f == "Y").sum()), n=lambda f: int((f == "N").sum()),
        m=lambda f: int((f == "MIXED").sum())).reset_index()

    case_of = s.drop_duplicates("CUSIP").set_index("CUSIP").CASE_ID
    year_of = s.drop_duplicates("CUSIP").set_index("CUSIP").EVENT_DATE.dt.year
    c["CASE_ID"] = c.CUSIP.map(case_of)
    # mutually exclusive classes (review round 2): A opposite answers across families; B every family Y;
    # C every family N; D no Y-vs-N split but a family's own holdings disagree. MIXED overlaps A and D.
    c["CLASS"] = np.select([(c.y > 0) & (c.n > 0), (c.n == 0) & (c.m == 0), (c.y == 0) & (c.m == 0)], ["A", "B", "C"], "D")

    def summ(c):
        e = c[c.nfam >= 2]
        sp = e[e.CLASS == "A"]
        rng = np.random.default_rng(SEED)
        g = e.groupby("CASE_ID").CLASS.agg(a=lambda k: int((k == "A").sum()), k="size")
        idx = rng.integers(0, len(g), size=(DRAWS, len(g)))
        bs = g.a.values[idx].sum(1) / g.k.values[idx].sum(1)
        cw = (g.a / g.k).values
        bcw = cw[rng.integers(0, len(cw), size=(DRAWS, len(cw)))].mean(1)
        top5 = g.k.nlargest(5).index
        loo = [(g.a.sum() - g.a[i]) / (g.k.sum() - g.k[i]) for i in g.index]
        y20 = e.CUSIP.map(year_of) == 2020
        return {"cells": int(len(c)), "cells_ge2_families": int(len(e)), "cross_family_split": int(len(sp)),
                "split_share": round(len(sp) / max(len(e), 1), 4), "all_families_Y": int((e.CLASS == "B").sum()),
                "all_families_N": int((e.CLASS == "C").sum()), "within_family_only": int((e.CLASS == "D").sum()),
                "cells_with_mixed_family": int((e.m > 0).sum()),
                "mixed_in_split": int(((e.m > 0) & (e.CLASS == "A")).sum()),
                "cases": int(e.CASE_ID.nunique()), "split_cases": int(sp.CASE_ID.nunique()),
                "split_ci": [round(float(x), 4) for x in np.percentile(bs, [2.5, 97.5])],
                "case_weighted": round(float(cw.mean()), 4),
                "case_weighted_ci": [round(float(x), 4) for x in np.percentile(bcw, [2.5, 97.5])],
                "leave_one_case_out": [round(float(min(loo)), 6), round(float(max(loo)), 6)],
                "excl_top5_cases": round(float(g.drop(top5).a.sum() / g.drop(top5).k.sum()), 4),
                "top5_cases_share_of_cells": round(float(g.k[top5].sum() / g.k.sum()), 4),
                "cells_2020": int(y20.sum()), "split_share_2020": round(float((e[y20].CLASS == "A").mean()), 4),
                "split_share_not2020": round(float((e[~y20].CLASS == "A").mean()), 6),
                "median_families": float(e.nfam.median())}

    res = {"all": summ(c), "bonds": summ(c[c.LOAN_CLASS == "BOND"]), "loans": summ(c[c.LOAN_CLASS == "PREPETITION"])}
    e = c[c.nfam >= 2].assign(XSPLIT=lambda d: (d.y > 0) & (d.n > 0))
    u = s.merge(e[["CUSIP", "RD", "XSPLIT"]], on=["CUSIP", "RD"], how="left")
    sp = fam.merge(e[e.XSPLIT][["CUSIP", "RD"]], on=["CUSIP", "RD"])
    g = sp.groupby("FAMILY").FF.agg(k="size", y=lambda f: int((f == "Y").sum()), n=lambda f: int((f == "N").sum()))
    g5 = g[g.k >= 5]
    res.update({"units_in_split_cells": int((u.XSPLIT == True).sum()),  # noqa: E712
                "unflagged_units_in_split_cells": int(((u.XSPLIT == True) & (u.F == "UNFLAGGED")).sum()),  # noqa: E712
                "split_cells_cases": int(s.merge(e[e.XSPLIT][["CUSIP", "RD"]], on=["CUSIP", "RD"]).CASE_ID.nunique()),
                "families_ge5_split_cells": int(len(g5)), "families_always_Y": int((g5.n == 0).sum()),
                "families_always_N": int((g5.y == 0).sum()), "families_both": int(((g5.y > 0) & (g5.n > 0)).sum())})
    # worked example: the bond-date with the most families on the smaller side (chosen by that rule only)
    b = c[(c.CLASS == "A") & (c.LOAN_CLASS == "BOND")]
    ex = b.loc[(b[["y", "n"]].min(axis=1) * 1000 + b.nfam).idxmax()]
    xo = obs[(obs.CUSIP == ex.CUSIP) & (obs.RD == ex.RD) & (obs.F != "BLANK")]
    res["example"] = {"cusip": ex.CUSIP, "rd": str(pd.Timestamp(ex.RD).date()), "name": s[s.CUSIP == ex.CUSIP].NAME.iat[0],
                      "petition": str(s[s.CUSIP == ex.CUSIP].EVENT_DATE.iat[0].date()), "families": int(ex.nfam),
                      **{k: {"families": int(xo[xo.F == f].FAMILY.nunique()), "funds": int((xo.F == f).sum()),
                             "median_price": round(float(xo[xo.F == f].PRICE.median()), 1),
                             "value_usd": float(xo[xo.F == f].VALUE.sum()),
                             "accessions": xo[xo.F == f].sort_values("VALUE", ascending=False).ACCESSION_NUMBER.head(3).tolist()}
                         for k, f in [("default", "FLAGGED"), ("not_default", "UNFLAGGED")]}}
    c.to_csv(O / "final_cross_family_cells.csv", index=False)
    return res


def main():
    w, aud, s = final_sample()
    obs = pd.read_parquet(R / "units/obs.parquet")
    obs["F"] = np.where(obs.DEF.fillna("").str.contains("Y"), "FLAGGED",
                        np.where(obs.DEF.fillna("") == "N", "UNFLAGGED", "BLANK"))
    ok = (obs.UNIT == "PA") & (obs.CUR == "USD") & (obs.PAYOFF == "Long") & (obs.BALANCE > 0)
    obs["PRICE"] = (obs.VALUE / obs.BALANCE * 100).where(ok)
    fd = pd.read_parquet(R / "units/fund_dates.parquet")
    s2 = s.copy()
    s2["CASE_NEXT_103_PUBLIC"] = s2[["CASE_NEXT_103_PUBLIC", "END_DATE"]].min(axis=1)
    per = persistence(s2, obs.dropna(subset=["CASE_ID"]), fd, None)
    per.to_csv(O / "final_persistence.csv", index=False)
    un = s[s.F == "UNFLAGGED"]
    frozen = json.loads((O / "CONF_result.json").read_text())
    audited = json.loads((O / "CONF_amendment2.json").read_text())["debtor_pre_emergence"]

    case = s.groupby("CASE_ID").agg(name=("NAME", "first"), petition=("EVENT_DATE", "first"), units=("F", "size"),
                                    unflagged=("F", lambda f: int((f == "UNFLAGGED").sum())),
                                    value=("VALUE", "sum"))
    case["share"] = case.unflagged / case.units
    case.sort_values("share").to_csv(O / "final_by_case.csv")
    fam = s.groupby("FAMILY").agg(name=("FAMILY_NAME", "first"), units=("F", "size"),
                                  unflagged=("F", lambda f: int((f == "UNFLAGGED").sum())), cases=("CASE_ID", "nunique"))
    fam["share"] = fam.unflagged / fam.units
    fam.sort_values("units", ascending=False).to_csv(O / "final_by_family.csv")
    yr = s.assign(Y=s.EVENT_DATE.dt.year).groupby("Y").agg(cases=("CASE_ID", "nunique"), units=("F", "size"),
                                                          unflagged=("F", lambda f: int((f == "UNFLAGGED").sum())))
    yr["share"] = (yr.unflagged / yr.units).round(4)
    yr.to_csv(O / "final_by_year.csv")
    loo = pd.Series({c: float((s[s.CASE_ID != c].F == "UNFLAGGED").mean()) for c in s.CASE_ID.unique()})
    top5c = case.units.nlargest(5).index
    top5f = fam.units.nlargest(5).index
    fam10 = fam[fam.units >= 10]
    case5 = case[case.units >= 5]
    days_first = (s.RD - s.PUBLIC_DATE).dt.days

    res = {
        "stages": {
            "FROZEN": {**frozen["primary"], "case_weighted": frozen["case_weighted"]["share"],
                       "value_weighted": frozen["value_weighted"]["share"]},
            "AUDITED": {**audited["primary"], "case_weighted": audited["case_weighted"]["share"],
                        "value_weighted": audited["value_weighted"]["share"]},
            "FINAL": {**boot_share(s), "case_weighted": boot_case_weighted(s), "value_weighted": boot_share(s, w="VALUE")}},
        "removed_by_audit": w[~w.index.isin(aud.index)].groupby(["LABEL", "RD_STATUS"]).agg(
            units=("F", "size"), unflagged=("F", lambda f: int((f == "UNFLAGGED").sum())),
            value=("VALUE", "sum")).reset_index().to_dict("records"),
        "removed_rolled_up": {"units": int((aud.LOAN_CLASS == "ROLLED_UP").sum()),
                              "unflagged": int(((aud.LOAN_CLASS == "ROLLED_UP") & (aud.F == "UNFLAGGED")).sum()),
                              "value": float(aud[aud.LOAN_CLASS == "ROLLED_UP"].VALUE.sum())},
        "final_counts": {"units": int(len(s)), "flagged": int((s.F == "FLAGGED").sum()), "unflagged": int(len(un)),
                         "cases": int(s.CASE_ID.nunique()), "cusips": int(s.CUSIP.nunique()),
                         "funds": int(s.FUND_KEY.nunique()), "families": int(s.FAMILY.nunique()),
                         "value_usd": float(s.VALUE.sum()), "unflagged_value_usd": float(un.VALUE.sum()),
                         "petition_years": [int(s.EVENT_DATE.dt.year.min()), int(s.EVENT_DATE.dt.year.max())],
                         "median_days_public_to_first_report": float(days_first.median())},
        "by_asset": {"BOND": boot_share(s[s.LOAN_CLASS == "BOND"]), "LOAN": boot_share(s[s.LOAN_CLASS == "PREPETITION"])},
        "cases": {"no_unit_flagged": int((case.unflagged == case.units).sum()),
                  "all_flagged": int((case.unflagged == 0).sum()),
                  "share_quartiles_ge5": [round(float(x), 4) for x in case5.share.quantile([.25, .5, .75])],
                  "n_ge5": int(len(case5))},
        "robustness": {"leave_one_case_out": [round(float(loo.min()), 4), round(float(loo.max()), 4)],
                       "excl_top5_cases": round(float((s[~s.CASE_ID.isin(top5c)].F == "UNFLAGGED").mean()), 4),
                       "excl_top5_families": round(float((s[~s.FAMILY.isin(top5f)].F == "UNFLAGGED").mean()), 4),
                       "top5_case_share_of_unflagged": round(float(un.groupby("CASE_ID").size().nlargest(5).sum() / len(un)), 4),
                       "top5_family_share_of_unflagged": round(float(un.groupby("FAMILY").size().nlargest(5).sum() / len(un)), 4),
                       "known_end_date_only": boot_share(s[s.RD_STATUS == "PRE_EMERGENCE"]),
                       "known_end_cases": int(s[s.RD_STATUS == "PRE_EMERGENCE"].CASE_ID.nunique())},
        "families": {"n_ge10": int(len(fam10)), "ge10_all_flagged": int((fam10.unflagged == 0).sum()),
                     "ge10_none_flagged": int((fam10.unflagged == fam10.units).sum()),
                     "ge10_share_quartiles": [round(float(x), 4) for x in fam10.share.quantile([.25, .5, .75])]},
        "persistence": {**{k: int((per.STATUS == k).sum()) for k in PERSIST}, "total": int(len(per)),
                        "median_days_public_to_flag": float(per.DAYS_PUBLIC_TO_FLAG.median()),
                        "window_ended_no_later_report": int(((per.STATUS == "WINDOW_ENDED_UNFLAGGED") &
                                                             (per.LATER_REPORTS_SEEN == 0)).sum()),
                        "window_ended_unflagged_ge1_later": int(((per.STATUS == "WINDOW_ENDED_UNFLAGGED") &
                                                                 (per.LATER_REPORTS_SEEN >= 1)).sum()),
                        "window_ended_unflagged_ge2_later": int(((per.STATUS == "WINDOW_ENDED_UNFLAGGED") &
                                                                 (per.LATER_REPORTS_SEEN >= 2)).sum()),
                        # holdings observed again while still held: flagged at the next report vs not
                        "observed_again_held": int(((per.STATUS == "FLAGGED_LATER") |
                                                    ((per.STATUS == "WINDOW_ENDED_UNFLAGGED") &
                                                     (per.LATER_REPORTS_SEEN >= 1))).sum()),
                        "flagged_at_next_report": int(((per.STATUS == "FLAGGED_LATER") &
                                                       (per.LATER_REPORTS_SEEN == 1)).sum())},
        "valuation": valuation(s, obs),
        "stale_own_price_carried": {"unflagged": int((s.STALE & (s.F == "UNFLAGGED")).sum()),
                                    "flagged": int((s.STALE & (s.F == "FLAGGED")).sum()),
                                    "with_pre_and_post_price": int((s.P_PRE.notna() & s.PRICE.notna()).sum())},
        "arrears": {"unflagged_with_arrears": int((un.ARR.fillna("").str.contains("Y")).sum()),
                    "flagged_with_arrears": int(((s.F == "FLAGGED") & s.ARR.fillna("").str.contains("Y")).sum())},
        "unflagged_pct_nav": {"median": float((un.VALUE / un.NET_ASSETS * 100).median()),
                              "p90": float((un.VALUE / un.NET_ASSETS * 100).quantile(.9))},
    }
    ov = pd.read_parquet(R / "units/obs_versions.parquet", columns=["FUND_KEY", "CUSIP", "RD", "VERSION", "IS_DEFAULT"])
    v = ov.merge(s[["FUND_KEY", "CUSIP", "RD"]], on=["FUND_KEY", "CUSIP", "RD"])
    vv = v.groupby(["FUND_KEY", "CUSIP", "RD", "VERSION"]).IS_DEFAULT.agg(lambda x: "Y" if "Y" in set(x) else "N")
    mv = vv.groupby(level=[0, 1, 2]).agg(["nunique", "size"])
    res["amendments"] = {"units_multi_version": int((mv["size"] > 1).sum()), "flag_changed": int((mv["nunique"] > 1).sum())}
    res["cross_family"] = cross_family(s, obs)
    # review round 3: reconcile the price comparison's holder-level split cells with Table 4's family classes
    pc = pd.read_csv(O / "final_split_cell_prices.csv", parse_dates=["RD"])[["CUSIP", "RD"]].assign(PRICED=True)
    cc = pd.read_csv(O / "final_cross_family_cells.csv", parse_dates=["RD"]).merge(pc, on=["CUSIP", "RD"], how="left")
    cc["PRICED"] = cc.PRICED.fillna(False).astype(bool)
    un_x = obs[(obs.F == "UNFLAGGED")].merge(cc[(cc.CLASS == "A") & ~cc.PRICED][["CUSIP", "RD"]], on=["CUSIP", "RD"])
    res["valuation"]["reconcile"] = {
        "class_A": int((cc.CLASS == "A").sum()), "class_A_priced": int(((cc.CLASS == "A") & cc.PRICED).sum()),
        "class_A_unpriced": int(((cc.CLASS == "A") & ~cc.PRICED).sum()),
        "class_D_priced": int(((cc.CLASS == "D") & cc.PRICED).sum()),
        "unpriced_zero_balance_cells": int(un_x.groupby(["CUSIP", "RD"]).BALANCE.max().le(0).sum()),
        "unpriced_non_pa_cells": int(un_x.groupby(["CUSIP", "RD"]).UNIT.agg(lambda u: "PA" not in set(",".join(u).split(","))).sum()),
        "unpriced_loans": int(((cc.CLASS == "A") & ~cc.PRICED & (cc.LOAN_CLASS != "BOND")).sum())}
    res["sample"] = {"units_2020": int((s.EVENT_DATE.dt.year == 2020).sum()),
                     "cases_known_end": int(s[s.RD_STATUS == "PRE_EMERGENCE"].CASE_ID.nunique()),
                     "cases_no_end": int(s[s.RD_STATUS == "NO_END_DATE"].CASE_ID.nunique()),
                     "units_no_end": int((s.RD_STATUS == "NO_END_DATE").sum())}
    (O / "FINAL.json").write_text(json.dumps(res, indent=1, default=str))
    s.to_parquet(O / "final_units.parquet")
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
