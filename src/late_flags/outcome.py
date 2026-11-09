"""Primary and secondary analyses of PROTOCOL.md for one split (DEV or CONF).

CONF runs only when data/interim/late_flags/PROTOCOL_SHA256 exists and matches src/late_flags/PROTOCOL.md.

Unit flag: FLAGGED if any lot reports IS_DEFAULT = Y; UNFLAGGED if all lots report N; BLANK otherwise
(counted, excluded from the share).

Usage: python src/late_flags/outcome.py DEV|CONF
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
UN = ROOT / "data/interim/late_flags/units"
OUT = ROOT / "data/interim/late_flags/outcome"
PROTO = Path(__file__).with_name("PROTOCOL.md")
SHA = ROOT / "data/interim/late_flags/PROTOCOL_SHA256"
SEED, DRAWS = 20261029, 2000


def flag(s):
    s = s.fillna("")
    return np.where(s.str.contains("Y"), "FLAGGED", np.where(s == "N", "UNFLAGGED", "BLANK"))


def price(df):
    ok = (df.UNIT == "PA") & (df.CUR == "USD") & (df.PAYOFF == "Long") & (df.BALANCE > 0)
    return (df.VALUE / df.BALANCE * 100).where(ok)


def boot_share(u, w=None, by="CASE_ID"):
    rng = np.random.default_rng(SEED)
    u = u.assign(_x=(u.F == "UNFLAGGED").astype(float), _w=1.0 if w is None else u[w].clip(lower=0))
    g = u.groupby(by).apply(lambda d: pd.Series({"x": (d._x * d._w).sum(), "w": d._w.sum()}))
    point = g.x.sum() / g.w.sum()
    idx = rng.integers(0, len(g), size=(DRAWS, len(g)))
    bs = g.x.values[idx].sum(1) / g.w.values[idx].sum(1)
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return {"share": round(float(point), 4), "lo": round(float(lo), 4), "hi": round(float(hi), 4),
            "n_units": int(len(u)), "n_cases": int(len(g))}


def boot_case_weighted(u):
    """Mean over cases of each case's unflagged share; bootstrap over cases."""
    rng = np.random.default_rng(SEED)
    cs = u.groupby("CASE_ID").F.agg(lambda f: (f == "UNFLAGGED").mean()).values
    bs = cs[rng.integers(0, len(cs), size=(DRAWS, len(cs)))].mean(1)
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return {"share": round(float(cs.mean()), 4), "lo": round(float(lo), 4), "hi": round(float(hi), 4),
            "n_cases": int(len(cs))}


def verdict(p):
    if p["share"] >= 0.10 and p["lo"] >= 0.05:
        return "OMISSION COMMON"
    if p["hi"] < 0.05:
        return "OMISSION RARE"
    return "INCONCLUSIVE"


def persistence(u, o, fd, ev):
    """S1: follow each unflagged unit over the fund's later reports up to EVENT_DATE + 365 days and before the
    case's next Item 1.03 8-K."""
    o_idx = o.set_index(["FUND_KEY", "CUSIP", "RD"])
    fdates = fd.groupby("FUND_KEY").RD.apply(lambda x: sorted(set(x)))
    case_cusips = o.groupby(["FUND_KEY", "CASE_ID"]).apply(lambda d: d.groupby("CUSIP").RD.min().to_dict())
    rows = []
    for r in u[u.F == "UNFLAGGED"].itertuples():
        end = r.EVENT_DATE + pd.Timedelta(days=365)
        if pd.notna(r.CASE_NEXT_103_PUBLIC):
            end = min(end, r.CASE_NEXT_103_PUBLIC)
        later = [d for d in fdates.get(r.FUND_KEY, []) if r.RD < d < end]
        status, k, t_flag = "WINDOW_ENDED_UNFLAGGED", 0, np.nan
        if not later and not [d for d in fdates.get(r.FUND_KEY, []) if d > r.RD]:
            status = "FUND_GONE"
        for k, d in enumerate(later, 1):
            key = (r.FUND_KEY, r.CUSIP, d)
            if key in o_idx.index:
                if "Y" in str(o_idx.loc[key, "DEF"]):
                    status, t_flag = "FLAGGED_LATER", (d - r.PUBLIC_DATE).days
                    break
                continue
            held = case_cusips.get((r.FUND_KEY, r.CASE_ID), {})
            new = [c for c, first in held.items() if c != r.CUSIP and first > r.RD and first <= d]
            status = "EXCHANGED_LINKED" if new else "EXITED_OR_UNLINKED_EXCHANGE"
            break
        rows.append({"CASE_ID": r.CASE_ID, "CUSIP": r.CUSIP, "FUND_KEY": r.FUND_KEY, "FAMILY": r.FAMILY,
                     "STATUS": status, "LATER_REPORTS_SEEN": k, "DAYS_PUBLIC_TO_FLAG": t_flag,
                     "DAYS_PUBLIC_TO_FIRST_RD": (r.RD - r.PUBLIC_DATE).days})
    return pd.DataFrame(rows)


def run(split):
    if split == "CONF":
        h = hashlib.sha256(PROTO.read_bytes()).hexdigest()
        if not SHA.exists() or SHA.read_text().split()[0] != h:
            sys.exit("CONF refused: protocol not frozen or changed since freezing")
    OUT.mkdir(parents=True, exist_ok=True)
    u = pd.read_parquet(UN / "units.parquet")
    u = u[u.SPLIT == split].copy()
    o = pd.read_parquet(UN / "obs.parquet")
    fd = pd.read_parquet(UN / "fund_dates.parquet")
    ov = pd.read_parquet(UN / "obs_versions.parquet")
    u["F"] = flag(u.DEF)
    u["PRICE"] = price(u)
    o["F"] = flag(o.DEF)
    o["PRICE"] = price(o)
    res = {"split": split, "flag_counts": u.F.value_counts().to_dict()}
    s = u[u.F != "BLANK"]
    p = boot_share(s)
    res["primary"] = {**p, "verdict": verdict(p)}
    res["case_weighted"] = boot_case_weighted(s)
    res["value_weighted"] = boot_share(s, w="VALUE")
    # distributions across issuer cases, fund families and petition years
    s["YEAR"] = s.EVENT_DATE.dt.year
    dist = {}
    for k, extra in [("CASE_ID", ["NAME", "EVENT_DATE"]), ("FAMILY", ["FAMILY_NAME"]), ("YEAR", [])]:
        t = s.groupby(k).agg(units=("F", "size"), unflagged=("F", lambda f: int((f == "UNFLAGGED").sum())),
                             cases=("CASE_ID", "nunique"), value_usd=("VALUE", "sum"),
                             unflagged_value_usd=("VALUE", lambda v: float(v[s.loc[v.index, "F"] == "UNFLAGGED"].sum())),
                             **{e: (e, "first") for e in extra})
        t["unflagged_share"] = (t.unflagged / t.units).round(4)
        t.sort_values("units", ascending=False).to_csv(OUT / f"{split}_by_{k.lower()}.csv")
        dist[k] = {"groups": int(len(t)), "share_quartiles_groups_ge5_units":
                   [round(float(x), 4) for x in t[t.units >= 5].unflagged_share.quantile([0.25, 0.5, 0.75])]}
    dist["YEAR"]["table"] = s.groupby("YEAR").apply(lambda g: {"units": int(len(g)), "cases": int(g.CASE_ID.nunique()),
                            "unflagged_share": round(float((g.F == "UNFLAGGED").mean()), 4)}).to_dict()
    res["distribution"] = dist
    res["by_asset"] = {a: boot_share(g) for a, g in s.assign(A=s.ASSET_CAT).groupby("A")} if "ASSET_CAT" in s else {}
    cf = s.groupby("CASE_ID").F.agg(lambda f: (f == "FLAGGED").mean())
    res["cases"] = {"n": int(len(cf)), "no_unit_flagged": int((cf == 0).sum()), "all_units_flagged": int((cf == 1).sum()),
                    "median_case_unflagged_share": round(float(1 - cf.median()), 4)}
    obs_cases = o.dropna(subset=["CASE_ID"])

    # S1 persistence
    ev = u[["CASE_ID", "EVENT_DATE", "PUBLIC_DATE"]].drop_duplicates()
    per = persistence(s, obs_cases, fd, ev)
    res["S1_persistence"] = {"status": per.STATUS.value_counts().to_dict() if len(per) else {},
                             "median_days_public_to_flag": float(per.DAYS_PUBLIC_TO_FLAG.median()) if len(per) else None,
                             "median_days_public_to_first_report": float(s.assign(d=(s.RD - s.PUBLIC_DATE).dt.days).d.median())}

    # S2 concentration (unflagged units and value)
    un = s[s.F == "UNFLAGGED"]
    conc = {}
    for k in ["CASE_ID", "FAMILY"]:
        n = un.groupby(k).size().sort_values(ascending=False)
        v = un.groupby(k).VALUE.sum().sort_values(ascending=False)
        names = un.groupby(k).FAMILY_NAME.first() if k == "FAMILY" else un.groupby(k).CASE_ID.first()
        conc[k] = {"groups": int(len(n)), "top5_unit_share": round(float(n.head(5).sum() / max(len(un), 1)), 4),
                   "top5_value_share": round(float(v.head(5).sum() / max(v.sum(), 1)), 4),
                   "top5": [{"id": i, "name": str(names.get(i, i)), "units": int(n[i]), "value_usd": float(v.get(i, 0))}
                            for i in n.head(5).index]}
        # unflagged rate within groups with >= 10 units
        tot = s.groupby(k).size()
        rate = (un.groupby(k).size() / tot).fillna(0)[tot >= 10]
        conc[k]["groups_ge10_units"] = int(len(rate))
        conc[k]["groups_ge10_all_flagged"] = int((rate == 0).sum())
        conc[k]["groups_ge10_none_flagged"] = int((rate == 1).sum())
    res["S2_concentration"] = conc

    # S3 flag disagreement / S4 valuation disagreement at the units' CUSIP x report-date cells
    cells = s[["CUSIP", "RD"]].drop_duplicates()
    oc = o.merge(cells, on=["CUSIP", "RD"])
    oc = oc[oc.F != "BLANK"]
    g = oc.groupby(["CUSIP", "RD"]).F.agg(lambda f: (f == "FLAGGED").sum()).rename("y").to_frame()
    g["n"] = oc.groupby(["CUSIP", "RD"]).size()
    g2 = g[g.n >= 2]
    res["S3_flag_disagreement"] = {"cells_ge2": int(len(g2)), "split_cells": int(((g2.y > 0) & (g2.y < g2.n)).sum()),
                                   "all_unflagged_cells": int((g2.y == 0).sum()), "all_flagged_cells": int((g2.y == g2.n).sum())}
    oc = oc.dropna(subset=["PRICE"])
    med = oc.groupby(["CUSIP", "RD"]).PRICE
    oc["N_P"] = med.transform("size")
    oc["SUM_P"] = med.transform("sum")
    # median of the other holders, computed per row
    oth = []
    for (c, d), grp in oc.groupby(["CUSIP", "RD"]):
        pr = grp.PRICE.values
        for i, idx in enumerate(grp.index):
            rest = np.delete(pr, i)
            oth.append((idx, np.median(rest) if len(rest) else np.nan))
    oc["OTHERS_MED"] = pd.Series(dict(oth))
    oc["GAP"] = oc.PRICE - oc.OTHERS_MED
    sp = oc[oc.groupby(["CUSIP", "RD"]).F.transform(lambda f: f.nunique() == 2)]
    by = sp.groupby(["CUSIP", "RD", "F"]).PRICE.median().unstack()
    d = (by.get("UNFLAGGED") - by.get("FLAGGED")).dropna() if len(by) else pd.Series(dtype=float)
    res["S4_valuation"] = {"split_cells_with_prices": int(len(d)),
                           "median_unflagged_minus_flagged_points": float(d.median()) if len(d) else None,
                           "share_cells_unflagged_higher_by_5pts": round(float((d > 5).mean()), 4) if len(d) else None,
                           "unflagged_gap_to_other_holders_median_points":
                               float(oc[oc.F == "UNFLAGGED"].GAP.median()) if len(oc) else None,
                           "flagged_gap_to_other_holders_median_points":
                               float(oc[oc.F == "FLAGGED"].GAP.median()) if len(oc) else None}

    # S5 stale marks: own last pre-event price carried forward; S6 magnitude
    oi = o.dropna(subset=["PRICE"]).drop(columns="CASE_ID")
    pre = (oi.merge(u[["CASE_ID", "CUSIP", "FUND_KEY", "EVENT_DATE"]].drop_duplicates(), on=["CUSIP", "FUND_KEY"])
           .query("RD <= EVENT_DATE").sort_values("RD").drop_duplicates(["CASE_ID", "CUSIP", "FUND_KEY"], keep="last")
           [["CASE_ID", "CUSIP", "FUND_KEY", "RD", "PRICE"]].rename(columns={"RD": "RD_PRE", "PRICE": "P_PRE"}))
    nxt = (oi.merge(u[["CASE_ID", "CUSIP", "FUND_KEY", "RD"]].rename(columns={"RD": "RD_U"}), on=["CUSIP", "FUND_KEY"])
           .query("RD > RD_U").sort_values("RD").drop_duplicates(["CASE_ID", "CUSIP", "FUND_KEY"], keep="first")
           [["CASE_ID", "CUSIP", "FUND_KEY", "RD", "PRICE", "F"]].rename(columns={"RD": "RD_NEXT", "PRICE": "P_NEXT",
                                                                                "F": "F_NEXT"}))
    w = s.merge(pre, on=["CASE_ID", "CUSIP", "FUND_KEY"], how="left").merge(nxt, on=["CASE_ID", "CUSIP", "FUND_KEY"], how="left")
    w["STALE"] = (w.PRICE - w.P_PRE).abs() < 0.01
    w["NEXT_CHANGE_PTS"] = w.P_NEXT - w.PRICE
    w["NEXT_CHANGE_USD"] = w.NEXT_CHANGE_PTS / 100 * w.BALANCE
    w["NEXT_CHANGE_BP_NAV"] = w.NEXT_CHANGE_USD / w.NET_ASSETS * 1e4
    st = w[w.STALE & w.PRICE.notna()]
    res["S5_stale"] = {
        "units_with_pre_and_post_price": int(w[w.P_PRE.notna() & w.PRICE.notna()].shape[0]),
        "stale_by_flag": st.F.value_counts().to_dict(),
        "stale_unflagged_next_change_points_median": float(st[st.F == "UNFLAGGED"].NEXT_CHANGE_PTS.median())
        if (st.F == "UNFLAGGED").any() else None,
        "stale_unflagged_next_markdown_usd_total": float(-st[st.F == "UNFLAGGED"].NEXT_CHANGE_USD.clip(upper=0).sum()),
        "stale_unflagged_next_markdown_bp_nav_median":
            float(-st[(st.F == "UNFLAGGED") & (st.NEXT_CHANGE_USD < 0)].NEXT_CHANGE_BP_NAV.median())
            if ((st.F == "UNFLAGGED") & (st.NEXT_CHANGE_USD < 0)).any() else None,
        "stale_unflagged_next_markdown_bp_nav_max":
            float(-st[st.F == "UNFLAGGED"].NEXT_CHANGE_BP_NAV.min()) if (st.F == "UNFLAGGED").any() else None}
    pct = (un.VALUE / un.NET_ASSETS * 100)
    res["S6_magnitude"] = {
        "unflagged_value_usd": float(un.VALUE.sum()), "flagged_value_usd": float(s[s.F == "FLAGGED"].VALUE.sum()),
        "unflagged_pct_nav_median": float(pct.median()) if len(pct) else None,
        "unflagged_pct_nav_p90": float(pct.quantile(0.9)) if len(pct) else None,
        "comparator_gap_usd_unflagged": float((oc[oc.F == "UNFLAGGED"].GAP / 100 * oc[oc.F == "UNFLAGGED"].BALANCE).sum())
        if len(oc) else None}

    # S7 arrears; S8 amendments
    arr = np.where(s.ARR.fillna("").str.contains("Y"), "Y", "N")
    res["S7_arrears"] = pd.crosstab(s.F, arr).to_dict()
    v = ov.merge(s[["FUND_KEY", "CUSIP", "RD"]], on=["FUND_KEY", "CUSIP", "RD"])
    vv = v.groupby(["FUND_KEY", "CUSIP", "RD", "VERSION"]).IS_DEFAULT.agg(lambda x: "Y" if "Y" in set(x) else "N")
    multi = vv.groupby(level=[0, 1, 2]).agg(["nunique", "size"])
    res["S8_amendments"] = {"units_with_multiple_versions": int((multi["size"] > 1).sum()),
                            "units_flag_changed_across_versions": int((multi["nunique"] > 1).sum())}
    # unresolved security-level obligations: every in-scope CUSIP of the split's cases with its resolution
    sec = pd.read_parquet(ROOT / "data/interim/late_flags/link/securities.parquet")
    sec = sec[sec.IN_SCOPE & sec.CASE_ID.isin(set(u.CASE_ID) | set(pd.read_parquet(UN / "units.parquet")
                                                                     .query("SPLIT == @split").CASE_ID))]
    uc = u.groupby("CUSIP").agg(units=("F", "size"), blank=("F", lambda f: int((f == "BLANK").sum())),
                                priced=("PRICE", lambda x: int(x.notna().sum())))
    sec = sec.merge(uc, left_on="CUSIP", right_index=True, how="left").fillna({"units": 0, "blank": 0, "priced": 0})
    sec["RESOLUTION"] = np.where(sec.units == 0, "NO_IN_WINDOW_REPORT",
                                 np.where(sec.blank == sec.units, "ALL_BLANK", "RESOLVED"))
    sec[["CASE_ID", "CUSIP", "ISSUER", "TITLE", "ASSET_CAT", "VIA", "units", "blank", "priced", "RESOLUTION"]].to_csv(
        OUT / f"{split}_securities.csv", index=False)
    res["securities"] = sec.RESOLUTION.value_counts().to_dict()
    res["units_unpriced"] = int(u.PRICE.isna().sum())
    w.to_parquet(OUT / f"{split}_units_scored.parquet")
    per.to_parquet(OUT / f"{split}_persistence.parquet")
    (OUT / f"{split}_result.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    run(sys.argv[1])
