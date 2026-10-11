# AgriLens — Dust or Drought?

Exploratory NDVI anomaly screening for a Nile Delta study area (615 real Sentinel-2 field-date records, 20 audited fields, split 9 train / 6 validation / 5 test by geography).

AgriLens demonstrates vegetation anomaly screening with image-quality awareness. It does **not** claim to have identified dust or drought damage: there are zero independently verified damage labels, so every flag is a screening signal for human review and the cause stays undetermined.

## Study area selection — why Egypt rather than Jordan?

AgriLens was developed by a Jordanian team, but **Egypt's Nile Delta was selected as the first research and demonstration site** because it provided a concrete, quality-audited dataset suitable for a reproducible proof of concept. The decision reflects the **availability and suitability of the project data**, not a claim that Egypt has a more important agricultural water problem than Jordan.

- **A relevant agricultural setting.** The Nile Delta contains intensively cultivated and irrigated agricultural land. Satellite-observed vegetation changes there are relevant to the question *“Dust or Drought?”* because water management, atmospheric interference, crop development, and field operations can all affect the apparent greenness signal.
- **Real observations rather than invented examples.** The released Egyptian study includes **615 audited Sentinel-2 field-date observations across 20 fields and 33 dates**, with environmental and image-quality context. These are actual study-area observations, not simulated Jordanian observations.
- **An established validation protocol.** The audited fields have an existing **geographic split of 9 training, 6 validation, and 5 held-out test fields**. Using the established study area lets the team evaluate a practical screening workflow while preserving data provenance and geographic separation.
- **A defensible, bounded demonstration.** The team's modeling and validation workflows can be checked against the same Egyptian field-date source, and suspicious satellite-scene effects can be distinguished from observations that warrant field inspection. This is more scientifically defensible than transferring unverified results to a different geography.

**Why not Jordan in this release?** Jordan is highly relevant to agricultural water scarcity and would be a valuable next study area. However, this release does **not** include a comparable, independently audited Jordanian field-date dataset and validation protocol. We therefore make **no claim to have trained, tested, or validated AgriLens in Jordan**.

**Path to Jordan:** Assemble Jordanian agricultural field boundaries and time-series satellite observations, characterize local dust and image-quality conditions, include irrigation and field-measured water-status information where available, and repeat geographic hold-out evaluation. This requires **new local validation**; the Egyptian results must not be assumed to transfer unchanged.

**Scientific limitation:** The current system flags unusual vegetation patterns for review. It **does not independently determine whether dust, drought, irrigation, crop phenology, harvesting, or image artefacts caused a specific anomaly**, because independently verified dust/drought crop-damage labels are unavailable.

## What is in this repository

| Path | Owner | Contents |
|---|---|---|
| `scripts/ndvi_anomaly_detection.py` | Rand | Forecasting-residual anomaly detector (v1.2.0) |
| `validation/` | Rama | Validated 615-row flags, scene QA, figures, report (unchanged) |
| `docs/index.html` | Nour | Interactive dashboard (open in a browser or serve with GitHub Pages) |
| `docs/modeling/` | Rand | Modeling README and code audit |
| `tests/` | all | 28 regression tests |
| `output/ndvi_anomaly_v1/` | generated | Reference run on the 615 real records |
| `CHANGELOG.md` | | What changed and why |

## Quick start

```bash
python -m pip install -r requirements-modeling.txt
python -m pytest -q tests
python scripts/ndvi_anomaly_detection.py \
  --input validation/data/agrilens_real_field_date_QA_gated_615.csv \
  --scene-qa validation/results/date_scene_QA.csv \
  --field-coords validation/results/field_geography.csv \
  --repo-root . --output-dir output/ndvi_anomaly_v1
```

## How the pieces fit together

- **Rand's detector** (15 raw flags on the real data, lower tail only): 10 quality-screened review candidates + 5 suspected scene artefacts on 17 May.
- **Rama's validation workflow** (36 raw flags): 23 review candidates (14 positive, 9 negative NDVI anomalies) + 13 suspected scene artefacts on 17 May.
- **Nour's dashboard** shows both as separate, labelled layers. The two methods are not forced to agree.

Details: `docs/modeling/README.md`, `docs/modeling/CODE_AUDIT.md`, `validation/README.md`.
