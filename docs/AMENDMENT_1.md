# Amendment 1 (post hoc): debtor-status audit of linked securities

Status: written 2026-10-29 after the single confirmation run, **before** any audited estimate was computed.
Its sha256 is appended to data/interim/late_flags/PROTOCOL_SHA256.

## Why

The confirmation run (protocol sha d1bbb2eb...) gave 30.3% [20.5, 39.8], verdict OMISSION COMMON. That
result stays on record as the pre-registered result. Reading the per-case table showed linkage errors that
the frozen rules let through:
- Frontier Communications: 220 units of Gates Global, a different company (all unflagged), and 155 units of
  an issuer reported only as "BF". Mechanism: funds that labelled other bonds with the debtor's name put
  those bonds' LEIs into the debtor LEI set, and the LEI validation then accepted their CUSIP-6.
- Ferrellgas: the notes are issued by Ferrellgas, L.P.; the petition was filed by Ferrellgas Partners, L.P.
  (to be verified by the audit). A fund's "N" on a non-debtor's bond is not an omission.

These errors bias the share upward. The audit can only remove or keep holdings; it does not reclassify flags.

## Audit rule

1. Unit of audit: (case, normalised modal issuer name) group of the confirmation units' CUSIPs
   (audit/issuer_groups.csv, 89 groups over 60 cases). Built without flags.
2. Labeller: an independent model agent, given the groups, the petition 8-K links, and public sources. It
   does not see default or arrears flags, prices or any result. Labels:
   - DEBTOR: the issuer (or a co-issuer) filed a petition in this case at or around the petition date;
   - NOT_DEBTOR_AFFILIATE: an affiliate of the debtor that did not file (e.g. operating subsidiary);
   - NOT_DEBTOR_OTHER: a different company;
   - UNCLEAR: cannot be determined from public sources; preserved as unresolved.
   Each label carries the evidence (quote and URL).
3. Audited estimate (labelled post hoc): the frozen primary estimator restricted to DEBTOR groups. Bounds:
   the same estimator with UNCLEAR groups added. Case-weighted and value-weighted shares, by asset, and S1
   persistence are recomputed on the same restriction. NOT_DEBTOR groups are reported, not dropped silently.
4. The frozen verdict thresholds are applied to the audited estimate descriptively and labelled post hoc.
5. A second, independent check: the labeller's DEBTOR/NOT_DEBTOR labels for a random 15 groups (seed 11) are
   re-labelled by a second agent; agreement is reported.

## Not allowed

No change to the event list, the window, the flag definition or the estimator. No widening of the sample.
