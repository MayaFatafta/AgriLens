"""Release-specific verifications. Run: python -m unittest discover -s scripts -p 'test_*.py' -v"""
import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from build_integrated_release import apply_qa_windows

class TestWindowSafety(unittest.TestCase):
    def case(self):
        return pd.DataFrame({'field_id':[12]*4,'date':['2025-01-01','2025-01-05','2025-01-10','2025-02-01'],
                             'ndvi_mean':[.5,.49,.45,.1],'source_observation_quality_ok':[True]*4,
                             'v2_ndvi_slope3_total':[np.nan,np.nan,-.05,-.39],
                             'v2_ndvi_dev_from_prev5_median':[np.nan,np.nan,np.nan,-.35],
                             'v2_cusum_neg':[0.,0.,-.03,-.37]})
    def test_long_gap_rejects_window_and_resets_cusum(self):
        d=apply_qa_windows(self.case())
        self.assertFalse(bool(d.qa_temporal_pair_ok.iloc[3]));self.assertTrue(pd.isna(d.qa_cusum_neg_reset.iloc[3]))
        self.assertTrue(pd.isna(d.qa_ndvi_slope3_total.iloc[3]))
        self.assertTrue(pd.isna(d.qa_ndvi_dev_from_prev5_median.iloc[3]))
    def test_three_observation_good_window(self):
        d=apply_qa_windows(self.case())
        self.assertTrue(bool(d.qa_window3_ok.iloc[2]));self.assertAlmostEqual(d.qa_ndvi_slope3_total.iloc[2],-.05)
    def test_future_value_change_no_prior_feature_change(self):
        a=self.case();b=self.case();b.loc[3,'ndvi_mean']=.88
        x=apply_qa_windows(a);y=apply_qa_windows(b)
        for c in ['qa_ndvi_slope3_total','qa_ndvi_dev_from_prev5_median','qa_cusum_neg_reset']:
            pd.testing.assert_series_equal(x[c].iloc[:3],y[c].iloc[:3])
    def test_bad_previous_quality_invalidates_slope(self):
        a=self.case();a.loc[1,'source_observation_quality_ok']=False
        d=apply_qa_windows(a)
        self.assertFalse(bool(d.qa_window3_ok.iloc[2]));self.assertTrue(pd.isna(d.qa_ndvi_slope3_total.iloc[2]))
    def test_repeated_fields_do_not_share_cusum(self):
        a=self.case().iloc[:3].copy();b=a.copy();b['field_id']=14;b['ndvi_mean']=[.6,.7,.8]
        d=apply_qa_windows(pd.concat([a,b],ignore_index=True))
        self.assertAlmostEqual(d.loc[d.field_id==14,'qa_cusum_neg_reset'].dropna().iloc[-1],0.)
        self.assertTrue(d.loc[d.field_id==12,'qa_cusum_neg_reset'].dropna().iloc[-1]<0)

if __name__=='__main__':unittest.main()
