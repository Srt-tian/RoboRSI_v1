"""Check acquisition budgets, split isolation and cross-fit label separation."""
import unittest
import numpy as np
from physics_rsi import (BASE_SEEDS, COUNTS, METHODS, TASKS, context, folds,
                         knn_regret, select_indices)


class AcquisitionTests(unittest.TestCase):
    def test_budget_balance_and_isolation(self):
        contexts = [context(i, 'pool') for i in range(COUNTS['pool'])]
        x = np.zeros((len(contexts),29))
        x[:,0] = [c['task']==TASKS[1] for c in contexts]
        x[:,3] = [c['delay']*.04 for c in contexts]
        scores = np.arange(len(x), dtype=float)
        for method in METHODS:
            selected = select_indices(x,scores,method)
            self.assertEqual(len(selected),180)
            self.assertEqual(len(set(selected)),180)
            for task in [0,1]:
                for long in [False,True]:
                    self.assertEqual(sum(x[i,0]==task and (x[i,3]>.8)==long for i in selected),45)
        sets = [{context(i,s)['seed'] for i in range(COUNTS[s])} for s in BASE_SEEDS]
        for i,a in enumerate(sets):
            self.assertTrue(min(a)>1000000)
            for b in sets[i+1:]:
                self.assertFalse(a&b)

    def test_folds_cover_all_task_stage_groups(self):
        rows = [dict(context=dict(task=TASKS[i%2]),stage=(i//2)%3) for i in range(120)]
        assignment = folds(rows)
        for task in TASKS:
            for stage in range(3):
                ix = [i for i,r in enumerate(rows) if r['context']['task']==task and r['stage']==stage]
                self.assertEqual(set(assignment[ix]),{0,1,2})
        x = np.zeros((40,29)); x[20:,0]=1
        error = np.r_[np.zeros(20),np.ones(20)]
        np.testing.assert_allclose(knn_regret(x,error,x),error)


if __name__=='__main__':
    unittest.main()
