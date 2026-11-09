# Amendment 2 (post hoc): security-level debtor identity, default status at the report date, review of
# influential groups

Status: written 2026-10-29 after the confirmation run and while the Amendment 1 labeller was still running,
**before** any audited estimate was computed. Its sha256 is appended to data/interim/late_flags/PROTOCOL_SHA256.
It supersedes Amendment 1 where they differ.

## Standing of the frozen result

The frozen confirmation output (30.3% [20.5, 39.8], OMISSION COMMON) stays in the record. Because linkage
errors were found after the run (Gates Global and "BF" inside Frontier; Ferrellgas, L.P. notes, a non-debtor:
Ferrellgas Partners, L.P. and Ferrellgas Partners Finance Corp. filed on 2021-01-11, the operating partnership did
not; plan effective 2021-03-30), the frozen verdict does **not** govern what is concluded. The source-verified,
post-hoc estimate below does, and it is never described as pre-registered.

## Changes to the audit (relative to Amendment 1)

1. **Security-level debtor identity.** The unit of the debtor decision is the CUSIP, not the issuer-name group.
   A group label is applied to a CUSIP only when no CUSIP-level evidence contradicts it; contradictory
   CUSIP-level evidence (issuer legal entity from the security's own documents, LEI or CUSIP-6 owner) governs.
2. **Default status at the report date.** For each case, the plan effective date (emergence), dismissal or
   conversion date is taken from the debtor's own 8-Ks. A unit counts toward the audited estimate only if its
   report date is on or after the petition date and before that date (no effective date found: kept and listed).
   Units after emergence are reported separately as POST_EMERGENCE. Reinstated or unimpaired debt is not
   treated as in default after the effective date.
3. **UNCLEAR is a sensitivity, not a bound.** Results are given for (a) DEBTOR only and (b) DEBTOR plus
   UNCLEAR, called a sensitivity estimate.
4. **Source review of every influential group.** Selection by size and exposure only, never by flags:
   groups with >= 25 confirmation units, or >= $25m of confirmation value, or among the largest groups until
   90% of units are covered (audit/group_influence.csv: 37 of 89 groups, 92.1% of units, 97.2% of value, 141 of
   206 CUSIPs). A second, independent source-based reviewer inspects every CUSIP in these groups (issuer legal
   entity, debtor status, case effective date) regardless of the first labeller's confidence. Disagreements
   between labeller and reviewer are resolved from the cited documents and listed; unresolved ones become UNCLEAR.
   The 15-group random re-label of Amendment 1 is dropped in favour of this.

## Interpretation rules

- "Currently in default" in N-PORT is a status at the report date. A debtor match plus a pre-emergence report
  date is the evidence used; it remains a strong external signal, not a legal finding about any fund.
- Arrears without a default flag (14 units) is reported descriptively; arrears or legally deferred interest
  need not be a current contractual default.
- Valuation (S4-S6): a zero median price gap shows that label disagreements are not generally accompanied by
  different marks; it does not show equivalent or correct valuations. No "late marks" or "stale NAV"
  conclusion either way beyond that.
- Persistence statuses are always given as five categories (FLAGGED_LATER, WINDOW_ENDED_UNFLAGGED,
  EXCHANGED_LINKED, EXITED_OR_UNLINKED_EXCHANGE, FUND_GONE) summing to the unflagged count, and persistence is
  restricted to pre-emergence reports.

## Publication rule (decided before the audited estimate)

- Substantial share survives with strong security-level evidence: short note; frozen 30.3% shown as the frozen
  output, corrected estimate as a post-hoc audit.
- Mismatch survives but contractual default at the report date cannot be established: frame as
  post-bankruptcy reporting differences; no "omission", "late flag" or manager-error language.
- Effect largely disappears or depends on UNCLEAR labels: no SSRN submission; keep internally.

Not allowed: rerunning confirmation, changing the event list, window, flag definition or estimator, widening
the population.
