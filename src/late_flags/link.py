"""Link independent bankruptcy events (8-K Item 1.03) to the prepetition debt securities funds held. Reads no
default or arrears flag: linkage uses issuer names, LEIs, CUSIPs and report dates only.

Event (issuer case): the first 8-K of a CIK that reports Item 1.03 and mentions Chapter 11 or Chapter 7. Later
Item 1.03 8-Ks of the same CIK within 3 years belong to the same case; the first of them (typically plan
confirmation) is CASE_NEXT_103_PUBLIC and closes the observation window.

Security link (method recorded per CUSIP):
  NAME: normalised N-PORT issuer name equals the normalised 8-K filer name (names of >= 2 tokens or >= 6 letters);
  CUSIP6: other CUSIPs with an issuer prefix of a NAME match;
  LEI: other holdings with an issuer LEI of a NAME match.
CUSIP-6s are validated against the debtor (see link()); only DBT/LON, no pass-throughs or CMBS.
Only cases whose 8-K text verifies a petition (verify_events.py); EVENT_DATE = petition date.
Prepetition: the CUSIP is held by at least one fund at a report date on or before EVENT_DATE. Titles mentioning
DIP / debtor-in-possession are dropped.

Outputs data/interim/late_flags/link/{events,securities}.parquet.
Usage: python src/late_flags/link.py
"""
import re
from pathlib import Path

import pandas as pd

from panel import norm_name

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "data/interim/late_flags/events"
PA = ROOT / "data/interim/late_flags/panel"
EX = ROOT / "data/interim/late_flags/extract"
OUT = ROOT / "data/interim/late_flags/link"


def cases():
    h = pd.read_parquet(EV / "8k_hits.parquet")
    h = h[h.ITEMS.str.contains(r"1\.03") & h.QUERY.isin(['"Chapter 11"', '"Chapter 7"'])].copy()
    h["EVENT_DATE"] = pd.to_datetime(h.EVENT_DATE, errors="coerce")
    h["PUBLIC_DATE"] = pd.to_datetime(h.PUBLIC_DATE, errors="coerce")
    h = h.dropna(subset=["EVENT_DATE"]).sort_values(["CIK", "PUBLIC_DATE", "ADSH"]).drop_duplicates("ADSH")
    rows = []
    for cik, g in h.groupby("CIK"):
        g = g.reset_index(drop=True)
        start = 0
        while start < len(g):
            first = g.iloc[start]
            same = g[(g.index > start) & (g.PUBLIC_DATE <= first.PUBLIC_DATE + pd.Timedelta(days=1095))]
            nxt = same[same.PUBLIC_DATE > first.PUBLIC_DATE + pd.Timedelta(days=7)]
            rows.append({"CASE_ID": f"{cik}_{first.EVENT_DATE.date()}", "CIK": cik,
                         "NAME": re.sub(r"\s*\(.*$", "", first.NAME).strip(), "FORM": first.FORM,
                         "ADSH": first.ADSH, "EVENT_DATE": first.EVENT_DATE, "PUBLIC_DATE": first.PUBLIC_DATE,
                         "N_103_FILINGS": 1 + len(same),
                         "CASE_NEXT_103_PUBLIC": nxt.PUBLIC_DATE.min() if len(nxt) else pd.NaT})
            start = (same.index.max() + 1) if len(same) else start + 1
    c = pd.DataFrame(rows)
    c["NAME_N"] = norm_name(c.NAME)
    return c


GENERIC = {"ENERGY", "INTERNATIONAL", "INTL", "GROUP", "COMMUNICATIONS", "HEALTH", "RESOURCES", "PETROLEUM", "OIL",
           "GAS", "TECHNOLOGIES", "TECHNOLOGY", "SYSTEMS", "MEDIA", "CAPITAL", "TRUST", "PARTNERS", "SERVICES",
           "FINANCE", "FIN", "AMERICA", "AMERICAN", "NATIONAL", "GLOBAL", "INDUSTRIES", "BRANDS", "RETAIL",
           "HOLDCO", "OPERATING", "PROPERTIES", "INCOME", "FINCO", "ISSUER", "ESCROW", "US", "USA", "NEW", "THE",
           "AND", "OF", "DRILLING", "OFFSHORE", "ENTERTAINMENT", "PHARMACEUTICALS", "THERAPEUTICS", "SCIENTIFIC"}


def tokens(s):
    return {t for t in s.split() if len(t) >= 3 and t not in GENERIC}


def link(c, iss):
    """Candidate CUSIP-6s from exact normalised-name matches and from the LEIs of those matches, kept only when
    the CUSIP-6's own holdings point to the debtor: its most common LEI is a debtor LEI, or at least half its
    holding rows carry an issuer name sharing a distinctive token with the debtor's name."""
    ok = (c.NAME_N.str.split().str.len() >= 2) | (c.NAME_N.str.replace(" ", "").str.len() >= 6)
    m = iss.merge(c[ok][["CASE_ID", "NAME_N"]], on="NAME_N")
    m = m[(m.CUSIP6.str.len() == 6) & ~m.CUSIP6.str.fullmatch(r"0+|9+|N/A.*")]
    lei = m[m.ISSUER_LEI.str.len() == 20].groupby(["CASE_ID", "ISSUER_LEI"]).n.sum().reset_index()
    via_lei = iss.merge(lei[["CASE_ID", "ISSUER_LEI"]], on="ISSUER_LEI")[["CASE_ID", "CUSIP6"]]
    cand = pd.concat([m[["CASE_ID", "CUSIP6"]].assign(VIA="NAME"), via_lei.assign(VIA="LEI")])
    cand = cand[(cand.CUSIP6.str.len() == 6) & ~cand.CUSIP6.str.fullmatch(r"0+|9+")].drop_duplicates(["CASE_ID", "CUSIP6"])
    i6 = iss[iss.CUSIP6.isin(set(cand.CUSIP6))]
    modal_lei = (i6[i6.ISSUER_LEI.str.len() == 20].groupby(["CUSIP6", "ISSUER_LEI"]).n.sum().reset_index()
                 .sort_values("n").drop_duplicates("CUSIP6", keep="last").set_index("CUSIP6").ISSUER_LEI)
    case_leis = lei.groupby("CASE_ID").ISSUER_LEI.apply(set)
    case_tok = c.set_index("CASE_ID").NAME_N.map(tokens)
    tot = i6.groupby("CUSIP6").n.sum()
    keep = []
    for r in cand.itertuples():
        lei_ok = modal_lei.get(r.CUSIP6) in case_leis.get(r.CASE_ID, set())
        ct = case_tok.get(r.CASE_ID, set())
        rows = i6[i6.CUSIP6 == r.CUSIP6]
        share = rows.n[rows.NAME_N.map(lambda s: bool(tokens(s) & ct))].sum() / tot[r.CUSIP6] if ct else 0.0
        keep.append(lei_ok or share >= 0.5)
    cand["VALID"] = keep
    x = cand[cand.VALID].drop(columns="VALID")
    # a CUSIP-6 reached by several cases is ambiguous (e.g. name collision or successive cases): unresolved
    amb = x.groupby("CUSIP6").CASE_ID.nunique()
    x["AMBIGUOUS"] = x.CUSIP6.map(amb) > 1
    return x, cand


def securities(x, c):
    want = set(x.CUSIP6)
    fm = pd.read_parquet(PA / "filings_master.parquet", columns=["ACCESSION_NUMBER", "RD", "LATEST"])
    fm = fm[fm.LATEST]
    parts = []
    for p in sorted(EX.glob("*_debt.parquet")):
        d = pd.read_parquet(p, columns=["ACCESSION_NUMBER", "ISSUER_CUSIP", "ISSUER_NAME", "ISSUER_TITLE",
                                        "MATURITY_DATE", "ASSET_CAT"])
        d["CUSIP"] = d.ISSUER_CUSIP.str.strip().str.upper()
        d = d[d.CUSIP.str[:6].isin(want) & (d.CUSIP.str.len() == 9)]
        parts.append(d.merge(fm, on="ACCESSION_NUMBER"))
    d = pd.concat(parts)
    d["CUSIP6"] = d.CUSIP.str[:6]
    s = d.groupby("CUSIP").agg(CUSIP6=("CUSIP6", "first"), TITLE=("ISSUER_TITLE", "first"),
                               ISSUER=("ISSUER_NAME", "first"), MATURITY=("MATURITY_DATE", "first"),
                               ASSET_CAT=("ASSET_CAT", lambda a: a.mode().iat[0]),
                               FIRST_RD=("RD", "min"), LAST_RD=("RD", "max")).reset_index()
    s = s.merge(x, on="CUSIP6").merge(c[["CASE_ID", "EVENT_DATE", "PUBLIC_DATE"]], on="CASE_ID")
    s["MATURITY_D"] = pd.to_datetime(s.MATURITY, errors="coerce")
    s["PREPETITION"] = s.FIRST_RD <= s.EVENT_DATE
    s["DIP"] = s.TITLE.fillna("").str.upper().str.contains(r"\bDIP\b|DEBTOR[- ]IN[- ]POSSESSION")
    s["MATURED_BEFORE_EVENT"] = s.MATURITY_D < s.EVENT_DATE
    s["NOT_CORP_DEBT"] = ~s.ASSET_CAT.isin(["DBT", "LON"]) | \
        s.TITLE.fillna("").str.upper().str.contains(r"PASS[- ]THRU|PASS[- ]THROUGH|\bPTT\b|MORTGAGE TRUST|\bCMBS\b|ISSUER LLC")
    s["IN_SCOPE"] = s.PREPETITION & ~s.DIP & ~s.MATURED_BEFORE_EVENT & ~s.AMBIGUOUS & ~s.NOT_CORP_DEBT
    return s


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    c = cases().merge(pd.read_parquet(EV / "verified.parquet")[["CASE_ID", "VERIFY", "PETITION_DATE"]], on="CASE_ID")
    c["EVENT_DATE_8K"] = c.EVENT_DATE
    c["EVENT_DATE"] = c.PETITION_DATE
    print("cases", len(c), c.VERIFY.value_counts().to_dict())
    c_all, c = c, c[c.VERIFY == "PETITION"].copy()
    iss = pd.read_parquet(PA / "issuers.parquet")
    x, cand = link(c, iss)
    cand.to_parquet(OUT / "cusip6_candidates.parquet")
    s = securities(x, c)
    c["N_CUSIP_IN_SCOPE"] = c.CASE_ID.map(s[s.IN_SCOPE].groupby("CASE_ID").size()).fillna(0).astype(int)
    c_all = c_all.merge(c[["CASE_ID", "N_CUSIP_IN_SCOPE"]], on="CASE_ID", how="left")
    c_all.to_parquet(OUT / "events.parquet")
    s.to_parquet(OUT / "securities.parquet")
    print("cases", len(c), "linked cases", int((c.N_CUSIP_IN_SCOPE > 0).sum()),
          "in-scope CUSIPs", int(s.IN_SCOPE.sum()), "by method", s[s.IN_SCOPE].VIA.value_counts().to_dict(),
          "candidate CUSIP6 rejected", int((~cand.VALID).sum()),
          "excluded", {k: int(s[k].sum()) for k in ["DIP", "MATURED_BEFORE_EVENT", "AMBIGUOUS", "NOT_CORP_DEBT"]},
          "not prepetition", int((~s.PREPETITION).sum()))


if __name__ == "__main__":
    main()
