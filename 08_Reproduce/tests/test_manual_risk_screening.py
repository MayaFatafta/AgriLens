import importlib.util
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('agrilens_manual_screen', ROOT / 'scripts/screen_field_risks.py')
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def sample():
    rows = []
    dates = ['2025-06-01', '2025-06-06', '2025-06-11', '2025-06-16', '2025-06-21']
    dust = [10, 40, 100, 300, 800]
    moisture = [.080, .060, .040, .020, .010]
    for fid, split, indexes in [(1, 'train', [0, 1, 2]), (2, 'validation', [3]), (3, 'test', [4])]:
        for idx in indexes:
            rows.append(dict(field_id=fid, date=dates[idx], ndvi_mean=.5-.04*idx,
                             ndmi_mean=.2-.05*idx, pixel_count=10,
                             coverage_ratio_vs_p90=1.0, low_coverage=False,
                             quarantined_polygon=False, dust_max_48h=dust[idx],
                             aod_max_48h=.1 + .04 * idx,
                             soil_moisture_28_to_100cm=moisture[idx],
                             split='train'))  # deliberately wrong validation/test splits
    m = pd.DataFrame({'field_id': [1, 2, 3], 'field_split': ['train', 'validation', 'test']})
    return pd.DataFrame(rows), m


class ProxyScreeningTests(unittest.TestCase):
    def test_real_inputs_reproducible_inventory(self):
        d = pd.read_csv(ROOT / 'inputs/field_date_analysis.csv')
        m = pd.read_csv(ROOT / 'inputs/egypt_emit_s2_field_alignment.csv')
        h = pd.read_csv(ROOT / 'inputs/egypt_hsi_s2_usable_fields.csv')
        r = mod.analyze(d, m, h)
        self.assertEqual(len(r['screened']), 615)
        self.assertEqual(r['screened'].field_id.nunique(), 20)
        self.assertEqual(len(r['hsi_context']), 14)
        self.assertEqual(len(r['by_date']), 33)
        self.assertEqual(int(r['report']['verified_independent_crop_damage_labels']), 0)
        self.assertTrue(r['screened'].verified_crop_damage_label.isna().all())
        self.assertTrue((r['screened'].label_status == 'NOT_VERIFIED_PROXY_ONLY').all())
        self.assertEqual(r['report']['historical_vs_audited_split_conflict_records'], 308)
        self.assertEqual(r['report']['high_priority_records'], 9)
        self.assertEqual(r['report']['screening_review_queue_records'], 196)

    def test_calibration_only_training_dates_no_holdout_leakage(self):
        d, m = sample()
        first = mod.analyze(d, m)
        # Change values exclusively on test and validation dates; training calibration unchanged.
        d.loc[d.field_id != 1, 'dust_max_48h'] = [9999, 0]
        d.loc[d.field_id != 1, 'soil_moisture_28_to_100cm'] = [.001, .999]
        second = mod.analyze(d, m)
        self.assertEqual(first['report']['thresholds'], second['report']['thresholds'])
        self.assertEqual(first['report']['thresholds']['dust_max_48h_high_train_unique_date_q75'], 70)
        self.assertEqual(first['report']['thresholds']['soil_moisture_28_to_100cm_low_train_unique_date_q25'], .05)

    def test_audited_split_overrides_bad_legacy_split(self):
        d, m = sample()
        r = mod.analyze(d, m)
        self.assertEqual(set(r['screened'].loc[r['screened'].field_id == 2, 'field_split']), {'validation'})
        self.assertEqual(set(r['screened'].loc[r['screened'].field_id == 3, 'field_split']), {'test'})
        self.assertEqual(int(r['screened'].split_mismatch_with_audited.sum()), 2)

    def test_duplicate_source_field_date_fails_closed(self):
        d, m = sample()
        with self.assertRaisesRegex(ValueError, 'Duplicate field_id'):
            mod.analyze(pd.concat([d, d.iloc[[0]]], ignore_index=True), m)

    def test_duplicate_master_fails_closed(self):
        d, m = sample()
        with self.assertRaisesRegex(ValueError, 'Duplicate field_id'):
            mod.analyze(d, pd.concat([m, m.iloc[[0]]]))

    def test_missing_first_observation_is_not_clean_negative(self):
        d, m = sample()
        r = mod.analyze(d, m)
        first = r['screened'].query('field_id == 1').iloc[0]
        self.assertFalse(bool(first.temporal_pair_usable))
        self.assertEqual(first.screening_category, 'insufficient_input_evidence')
        self.assertFalse(bool(first.damage_label_verified))

    def test_no_invented_dust_drought_ground_truth(self):
        d, m = sample()
        r = mod.analyze(d, m)
        self.assertNotIn('confirmed_crop_damage', r['screened'].screening_category.unique().tolist())
        self.assertTrue(r['screened'].verified_crop_damage_label.isna().all())
        self.assertFalse(r['report']['supervised_damage_classification_ready'])

    def test_noneligible_fields_not_screened(self):
        d, m = sample()
        unknown = d.iloc[[0]].copy()
        unknown['field_id'] = 991
        r = mod.analyze(pd.concat([d, unknown], ignore_index=True), m)
        self.assertEqual(r['report']['excluded_rows_outside_eligible_field_ids'], 1)
        self.assertNotIn(991, set(r['screened'].field_id))

    def test_bad_source_quality_suppresses_risk_flags(self):
        d, m = sample()
        d.loc[d.field_id == 2, 'low_coverage'] = True
        r = mod.analyze(d, m)
        t = r['screened'].loc[r['screened'].field_id == 2].iloc[0]
        self.assertEqual(t.screening_category, 'insufficient_observation_quality')
        self.assertFalse(bool(t.high_modeled_dust_context))
        self.assertFalse(bool(t.vegetation_decline_detected))

    def test_inconsistent_aoi_environment_is_rejected(self):
        d, m = sample()
        extra = d.iloc[[0]].copy()
        extra['field_id'] = 3
        extra['dust_max_48h'] = 999
        with self.assertRaisesRegex(ValueError, 'inconsistent'):
            mod.analyze(pd.concat([d, extra], ignore_index=True), m)

    def test_invalid_thresholds_fail(self):
        d, m = sample()
        with self.assertRaisesRegex(ValueError, 'Invalid predeclared'):
            mod.analyze(d, m, ndvi_drop=.04)


if __name__ == '__main__':
    unittest.main()
