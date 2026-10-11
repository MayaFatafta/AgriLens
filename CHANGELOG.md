# Change log

## 1.2.0 — integration corrections

**Problems resolved**

1. **Wrong split column.** Auto-detection picked `historical_split_recorded` (13 train / 7 test, no validation) and the run failed on the real table. Now `field_split` (9/6/5) has priority; ambiguity or invalid audited labels raise a clear error.
2. **Scene artefacts in the review queue.** The five model flags on 17 May (AOT 0.85) are marked as suspected scene artefacts needing image review. Raw flags are kept (`all_split_anomaly_flags.csv`); the screened queue is `quality_screened_review_queue.csv`.
3. **Unreliable GeoJSON.** Alerts are joined to audited field coordinates by field ID; only valid WGS84 points are written, the rest stay unmapped with an audit reason. Result on real data: 15 of 15 flags mapped.
4. **Dashboard grouping.** The 23 review candidates are split into 14 positive and 9 negative anomalies (direction filter, arrows, direction-aware advice). Scene artefacts remain a separate category. A new section compares Rama's validation flags with Rand's detector flags. Existing maps and charts are untouched.
5. **Tests and documentation.** 28 tests (was 7); README, code audit and requirements updated.

**Not changed:** the 615 observations, the 20 fields, the geographic assignments, the two distinct methods, or any metric value.

**Open items for the team**

- The corrected model run scores 152 test pairs (persistence MAE 0.02958, Ridge MAE 0.03092); the dashboard benchmark wording and older notes cite 37 pairs. The pair construction differs; reconcile before quoting either.
- 34 pixel-level dates versus 33 field-table dates remain to be reconciled by the data owners.
- Field coordinates are centroids for orientation, not field boundaries.
