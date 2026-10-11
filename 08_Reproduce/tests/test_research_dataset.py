import json
import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import build_research_dataset as builder


class TestAgriLensResearchDataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.features = pd.read_csv(ROOT/'outputs'/'next_ndvi_regression.csv', parse_dates=['date','target_date'], dtype={'field_id':str})
        cls.inv = pd.read_csv(ROOT/'outputs'/'sampling_frame_and_splits.csv', dtype={'field_id':str})
        cls.src = pd.read_csv(ROOT/'inputs'/'field_date_analysis.csv',parse_dates=['date'], dtype={'field_id':str})
        cls.geos = gpd.read_file(ROOT/'inputs'/'ftw_aoi_fields_with_crosswalk.geojson').to_crs(32636)

    def test_target_is_next_observed_field_ndvi(self):
        ref = self.src.sort_values(['field_id','date']).copy()
        ref['next_ndvi_expected']=ref.groupby('field_id').ndvi_mean.shift(-1)
        ref['next_date_expected']=ref.groupby('field_id').date.shift(-1)
        m=self.features.merge(ref[['field_id','date','next_ndvi_expected','next_date_expected']], on=['field_id','date'],validate='one_to_one')
        self.assertEqual(len(m),len(self.features))
        np.testing.assert_allclose(m.target_ndvi_next,m.next_ndvi_expected)
        self.assertTrue((m.target_date==m.next_date_expected).all())

    def test_all_fields_disjoint_across_splits(self):
        assignments=self.features.groupby('field_id').ml_split.nunique()
        self.assertEqual(assignments.max(),1)
        self.assertFalse(self.features.field_id.isin(['1665168']).any())

    def test_date_and_target_time_separation(self):
        cutoff=pd.Timestamp('2025-08-01')
        trainval=self.features[self.features.ml_split!='test']
        test=self.features[self.features.ml_split=='test']
        self.assertTrue((trainval.target_date<cutoff).all())
        self.assertTrue((test.date>=cutoff).all())
        self.assertTrue((self.features.target_date>self.features.date).all())
        self.assertTrue(self.features.target_horizon_days.between(3,18).all())

    def test_polygon_separations_at_least_100m(self):
        geom=self.geos[self.geos.field_id.notna()][['field_id','geometry']].copy()
        geom.field_id=geom.field_id.astype(str)
        merged=geom.merge(self.inv[['field_id','split_group']],on='field_id',validate='one_to_one')
        for a,b in [('train','validation'),('train','test'),('validation','test')]:
            aa=merged[merged.split_group==a].geometry
            bb=merged[merged.split_group==b].geometry
            self.assertGreaterEqual(min(x.distance(y) for x in aa for y in bb),100.)

    def test_no_future_data_columns_as_features(self):
        forbidden={'target_date','target_ndvi_next','target_horizon_days','field_id','ml_split','coverage_ratio_vs_p90','date','screening_label'}
        self.assertTrue(forbidden.isdisjoint(builder.FEATURES))
        self.assertTrue(set(builder.FEATURES).issubset(self.features.columns))

    def test_original_data_preserved(self):
        rep=json.loads((ROOT/'outputs'/'representation_leakage_audit.json').read_text())
        self.assertEqual(rep['original_pixel_observations'],707580)
        self.assertEqual(rep['original_pixel_split_crosses_fields'],15)
        self.assertEqual(rep['retained_descriptive_field_dates'],707)
        self.assertEqual(rep['modeling_field_counts']['excluded_buffer'],3)

    def test_three_splits_nonempty(self):
        groups=self.features.groupby('ml_split').agg(n=('field_id','size'),fields=('field_id','nunique'))
        for sp in ['train','validation','test']:
            self.assertGreaterEqual(groups.loc[sp,'fields'],2)
            self.assertGreaterEqual(groups.loc[sp,'n'],8)

    def test_smoke_rebuild_reproducible(self):
        f=builder.prepare_geometry(ROOT/'inputs'/'ftw_aoi_fields_with_crosswalk.geojson',set(self.src.field_id))
        inv,gaps=builder.geo_splits(f,100)
        again=builder.assemble_field_regression(self.src,inv)
        self.assertEqual(len(again),len(self.features))
        self.assertEqual(again.ml_split.value_counts().to_dict(),self.features.ml_split.value_counts().to_dict())

if __name__=='__main__':unittest.main()
