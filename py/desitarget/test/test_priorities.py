import unittest
import numpy as np

from astropy.table import Table

from desitarget import desi_mask, bgs_mask, mws_mask, obsmask
from desitarget.targets import calc_priority

class TestPriorities(unittest.TestCase):
    
    def setUp(self):
        dtype = [
            ('DESI_TARGET',np.int64),
            ('BGS_TARGET',np.int64),
            ('MWS_TARGET',np.int64),
            ('Z',np.float32),
            ('ZWARN',np.float32),
        ]
        self.targets = Table(np.zeros(3, dtype=dtype))
            
    def test_priorities(self):
        t = self.targets
        #- No targeting bits set is priority=0
        self.assertTrue(np.all(calc_priority(t) == 0))
        
        #- test QSO > LRG > ELG
        t['DESI_TARGET'] = desi_mask.ELG
        self.assertTrue(np.all(calc_priority(t) == desi_mask.ELG.priorities['UNOBS']))
        t['DESI_TARGET'] |= desi_mask.LRG
        self.assertTrue(np.all(calc_priority(t) == desi_mask.LRG.priorities['UNOBS']))
        t['DESI_TARGET'] |= desi_mask.QSO
        self.assertTrue(np.all(calc_priority(t) == desi_mask.QSO.priorities['UNOBS']))
        
        #- different states -> different priorities
        t['DESI_TARGET'] = desi_mask.BGS_ANY
        t['BGS_TARGET'] |= bgs_mask.BGS_FAINT
        t['NUMOBS'] = [0, 1, 1]
        t['ZWARN'] = [1, 1, 0]
        p = calc_priority(t)

        self.assertEqual(p[0], bgs_mask.BGS_FAINT.priorities['UNOBS'])
        self.assertEqual(p[1], bgs_mask.BGS_FAINT.priorities['MORE_ZWARN'])
        self.assertEqual(p[2], bgs_mask.BGS_FAINT.priorities['MORE_ZGOOD'])
        ### BGS_FAINT: {UNOBS: 2000, MORE_ZWARN: 2200, MORE_ZGOOD: 2300}
        
        #- Done is Done, regardless of ZWARN
        t['DESI_TARGET'] = desi_mask.BGS_ANY
        t['BGS_TARGET'] = bgs_mask.BGS_BRIGHT  #- only one obs needed
        t['NUMOBS'] = [0, 1, 1]
        t['ZWARN'] = [1, 1, 0]
        p = calc_priority(t)        
                
        self.assertEqual(p[0], bgs_mask.BGS_BRIGHT.priorities['UNOBS'])
        self.assertEqual(p[1], bgs_mask.BGS_BRIGHT.priorities['DONE'])
        self.assertEqual(p[2], bgs_mask.BGS_BRIGHT.priorities['DONE'])
        ### BGS_BRIGHT: {UNOBS: 2100, MORE_ZWARN: 2200, MORE_ZGOOD: 2300}

    def test_mask_priorities(self):
        for mask in [desi_mask, bgs_mask, mws_mask]:
            for name in mask.names():
                if name == 'SKY' or name.startswith('STD') \
                    or name in ['BGS_ANY', 'MWS_ANY', 'ANCILLARY_ANY']:
                    self.assertEqual(mask[name].priorities, {}, 'mask.{} has priorities?'.format(name))
                else:
                    for state in obsmask.names():
                        self.assertIn(state, mask[name].priorities,
                            '{} not in mask.{}.priorities'.format(state, name))

if __name__ == '__main__':
    unittest.main()
