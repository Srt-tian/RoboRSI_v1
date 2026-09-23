"""Audit paired MuJoCo labels, split isolation and checkpoint provenance."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np


def main():
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path);args=parser.parse_args();root=args.run
    splits={name:json.loads((root/(name+'.json')).read_text()) for name in ['train','validation','test','delay']}
    seen=set()
    for name,rows in splits.items():
        seeds={r['context']['seed'] for r in rows}
        assert len(seeds)==len(rows) and not seen.intersection(seeds), 'split leakage'
        seen.update(seeds)
        for row in rows:
            assert len(row['x'])==12
            assert row['context']['split']==name
            expected=1-np.asarray(row['success'],float)+row['context']['time_price']*np.asarray(row['duration'])
            np.testing.assert_allclose(expected,row['cost'],atol=1e-12)
    protocol=json.loads((root/'frozen_protocol.json').read_text())
    for seed,expected in protocol['checkpoints'].items():
        assert hashlib.sha256((root/f'model_{seed}.pt').read_bytes()).hexdigest()==expected
    replay_count=0
    for path in (root.parent/'judge_001_replay').glob('*.json.gz'):
        with gzip.open(path,'rt') as f:record=json.load(f)
        rows=splits[record['context']['split']];source=rows[record['context']['index']];a=record['choice']
        assert record['success']==source['success'][a], 'replay differs from benchmark'
        assert abs(record['duration_s']-source['duration'][a])<1e-8
        assert all(abs(t['t']-(i+1)*.04)<1e-8 for i,t in enumerate(record['trace']))
        if record['success']:assert all(x['success'] for x in record['trace'][-10:])
        replay_count+=1
    contrasts=[]
    for split in ['test','delay']:
        rows=splits[split];decisions=json.loads((root/(split+'_decisions.json')).read_text())['choices']
        cost=np.asarray([r['cost'] for r in rows]);ix=np.arange(len(rows))
        learned=np.mean([cost[ix,decisions[f'judge_seed{s}']] for s in [11,22,33]],axis=0)
        for task in ['FetchPush-v4','FetchPickAndPlace-v4']:
            mask=np.asarray([r['context']['task']==task for r in rows])
            for baseline in ['always_fast','always_accurate','uncertainty_rule']:
                delta=(learned-cost[ix,decisions[baseline]])[mask]
                rng=np.random.default_rng(1926)
                boot=np.mean(delta[rng.integers(0,len(delta),(3000,len(delta)))],axis=1)
                contrasts.append({'split':split,'task':task,'contrast':'judge_mean_minus_'+baseline,
                                  'difference':float(delta.mean()),'ci95':np.quantile(boot,[.025,.975]).tolist(),
                                  'unit':'paired scene; averaged three fixed training seeds','scenes':len(delta)})
    result={'split_contexts':{k:len(v) for k,v in splits.items()},'split_isolation':'passed','checkpoint_hashes':'passed',
            'replay_matches':replay_count,'cost_identity':'passed','contrasts':contrasts,
            'note':'Post-hoc descriptive paired bootstrap, no multiplicity correction; not a trained-seed population interval.'}
    (root/'audit.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
