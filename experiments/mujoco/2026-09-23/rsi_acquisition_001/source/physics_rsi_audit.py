"""Audit the complete physical-label archive of the offline acquisition study."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np


def read(path):
    return json.loads(path.read_text())


def audit(root, output):
    selection = read(root/'selection.json')
    pool = read(root/'pool.json')
    frozen = read(root/'frozen_protocol.json')
    for name in ['selection','acquired','validation']:
        assert hashlib.sha256((root/(name+'.json')).read_bytes()).hexdigest() == frozen[name+'_sha256']
    assert hashlib.sha256((root/'pool.json').read_bytes()).hexdigest() == selection['pool_sha256']
    union = set()
    for name, indices in selection['indices'].items():
        assert len(indices) == len(set(indices)) == 180
        for task in [0,1]:
            for long in [False,True]:
                assert sum(pool[i]['x'][0] == task and (pool[i]['x'][3] > .8) == long for i in indices) == 45
        union.update(indices)
    acquired = read(root/'acquired.json')
    assert {r['context']['index'] for r in acquired} == union
    for row in acquired:
        original = pool[row['context']['index']]
        for key in ['context','x','stage','stage_reached','state_sha256']:
            assert row[key] == original[key]
    all_seeds = {r['context']['seed'] for r in pool}
    checks, counts = 0, {}
    for split in ['pilot','validation','acquired','test','delay']:
        rows = read(root/(split+'.json'))
        seeds = {r['context']['seed'] for r in rows}
        assert len(seeds) == len(rows)
        if split != 'acquired':
            assert not seeds & all_seeds
            all_seeds.update(seeds)
        counts[split] = len(rows)
        for row in rows:
            c = row['context']
            path = root/'traces'/f"{c['split']}_{c['index']:05d}.json.gz"
            with gzip.open(path,'rt') as stream:
                record = json.load(stream)
            assert record['context'] == c
            assert len(record['branches']) == 3
            assert all(len(row[key]) == 3 for key in ['success','duration','cost'])
            state = np.asarray(record['snapshot']['state'],dtype=np.float64)
            assert hashlib.sha256(state.tobytes()).hexdigest() == row['state_sha256']
            for a,branch in enumerate(record['branches']):
                assert branch['state_sha256'] == row['state_sha256']
                assert 1 <= len(branch['trace']) <= 150
                streak = 0
                for k,step in enumerate(branch['trace']):
                    assert abs(step['t']-(k+1)*.04)<1e-9
                    assert np.isfinite(step['qpos']).all() and np.isfinite(step['qvel']).all()
                    assert np.max(np.abs(step['action']))<=1
                    streak = streak+1 if step['success'] else 0
                assert (streak>=10) == branch['success'] == row['success'][a]
                assert abs(branch['duration_s']-len(branch['trace'])*.04)<1e-9
                assert abs(branch['duration_s']-row['duration'][a])<1e-9
                expected = float(not branch['success'])+c['time_price']*branch['duration_s']
                assert abs(expected-row['cost'][a])<1e-9
                checks += 1
    result = dict(status='passed', complete_physical_branches_checked=checks, context_counts=counts,
                  unique_acquired=len(union), acquisition_budget_per_method=180,
                  task_delay_balance='passed', candidate_pool_identity='passed', split_seed_isolation='passed',
                  scope='All IDC physical traces; model checkpoint hashes independently checked by evaluation on training host')
    output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    assert not args.output.exists()
    audit(args.run,args.output)
