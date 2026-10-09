# Bias mitigation verification and acceptance

| Bias threat | Evidence from Egypt HSI+S2 audit | Mitigation | Verification decision |
| --- | --- | --- | --- |
| Duplicate and malformed spectral records | 14 × 232 = 3248 complete records; zero duplicate keys | Script rejects duplicates, NaNs, nonfinite values, out-of-range reflectance | PASS (for derived complete table only) |
| Missing spectral channels | Eight wavelengths missing in all 14 fields in preceding 240-band export | Remove only in separately documented 232-band modeling view; preserve raw | PASS with provenance |
| Missing satellite coverage | 6 of 20 eligible fields without valid EMIT pixels; all in training | Master availability table, prioritized additional imagery and no falsified imputation | RESIDUAL SELECTION BIAS |
| Unequal field coverage | Two fields < 50% valid EMIT centers | Coverage flags, include/exclude sensitivity analysis; do not drop silently | RESIDUAL BIAS |
| Split leakage | 10/14 historical vs authoritative split conflicts | Use audited `field_split`; train-only scaler fit; exclude IDs/date/split/quality context as predictive covariates | TECHNICAL CONTROLS PASS |
| Sampling representativeness | 3/9 train, 6/6 val, 5/5 test coverage; geographically clustered | Do not claim Egypt-wide representation, sample additional genuine fields | FAIL FOR REPRESENTATIVENESS |
| Pseudo-label circularity | No verified dust/drought injury labels | Independent evidence, second adjudicator, reject proxy-only labels | FAIL FOR SUPERVISED CLASSIFICATION |
| Class imbalance | No actual classes yet | Class count/evidence gate only after independent labels | NOT ASSESSABLE |
| High dimensionality | 232 spectral wavelengths but 3 training fields | 12 interpretable illustrative features, no performance claim | NOT ENOUGH TRAINING FIELDS |
| False sensor agreement | 60 m EMIT field medians June15 vs 20 m Sentinel means June16 | Preserve sensor/date labels; exploratory scatterplot only | INTERPRETATION LIMITED |
| Meteorological confounding | Environmental features share single S2 date and constant values | Exclude constants from cross-field training features; retain in context | PASS FOR EXPLORATORY VIEW |

## Hard stop

Do not report supervised dust-versus-drought accuracy from the current data. A held-out number with 3 HSI train fields, no independent labels, or synthetic classes would not demonstrate a validated classifier.

## Data artifact vs scientific evidence

A correctly generated CSV with all zeros missing does not imply missing-at-random, balanced train/test coverage, or ecological representativeness. The artifacts here document both what was checked and what remains unsupported.
