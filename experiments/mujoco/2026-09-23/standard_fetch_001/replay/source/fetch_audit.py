"""Audit archived full-reset Fetch episodes without running new dynamics."""
import argparse
import concurrent.futures
import gzip
import hashlib
import json
import os
from pathlib import Path

os.environ['OPENBLAS_NUM_THREADS'] = '1'
import numpy as np
from fetch_robustness import choice
from fetch_sensors import REGIMES, EstimatorBank, SensorTape
from fetch_standard import FixedSkill, write


def audit(path):
    with gzip.open(path, 'rt') as f:
        r = json.load(f)
    trace = r['trace']
    assert len(trace) == 50
    skill = FixedSkill(r['task'], r['config'])
    before = r['initial']['obs']
    grip, obj, goal = (np.array(before['observation'][:3]),
                       np.array(before['achieved_goal']), np.array(before['desired_goal']))
    robust = 'regime' in r
    if robust:
        tape = SensorTape(r['seed'], r['regime'])
        bank = EstimatorBank(REGIMES[r['regime']])
    for i, state in enumerate(trace):
        assert state['step'] == i + 1 and abs(state['t'] - (i + 1) * .04) < 1e-12
        assert not state['terminated'] and state['truncated'] == (i == 49)
        assert np.isfinite(state['qpos']).all() and np.isfinite(state['qvel']).all()
        assert np.max(np.abs(state['action'])) <= 1
        if robust:
            packet = tape.sample(obj)
            for name in ['fast', 'precise']:
                expected, actual = getattr(packet, name), state[name]
                assert (expected is None) == (actual is None)
                if actual is not None:
                    np.testing.assert_array_equal(expected, actual)
            assert state['precise_step'] == packet.precise_step
            assert packet.precise_step is None or packet.precise_step <= i
            estimates = bank.ingest(packet)
            np.testing.assert_allclose(estimates, state['estimates'], atol=1e-12, rtol=0)
            np.testing.assert_allclose(bank.ages(i), state['ages_s'], atol=1e-12, rtol=0)
            np.testing.assert_allclose([np.diag(f.covs[-1]) for f in bank.filters],
                                       state['covariance_diagonal'], atol=1e-12, rtol=0)
            selected = choice(r['method'], r['task'], skill.stage)
            assert state['decision_stage'] == skill.stage and selected == state['selected']
            estimate = estimates[selected]
            assert abs(np.linalg.norm(estimate - obj) - state['estimation_error_m']) < 1e-12
        else:
            estimate = obj
        np.testing.assert_array_equal(skill.action(grip, estimate, goal), state['action'])
        assert skill.stage == state['stage']
        distance = float(np.linalg.norm(np.asarray(state['object']) - goal))
        assert abs(distance - state['distance']) < 1e-12
        assert state['success'] == (distance < .05)
        assert state['reward'] == -float(distance > .05)
        grip, obj = np.array(state['grip']), np.array(state['object'])
        np.testing.assert_array_equal(goal, state['goal'])
    assert r['success'] == trace[-1]['success']
    assert r['ever_success'] == any(s['success'] for s in trace)
    assert r['last10_success'] == all(s['success'] for s in trace[-10:])
    assert r['final_distance'] == trace[-1]['distance']
    if robust:
        assert abs(r['estimation_rmse_m'] - np.sqrt(np.mean([s['estimation_error_m']**2 for s in trace]))) < 1e-12
    identity = (r['task'], r['seed'])
    initial_hash = hashlib.sha256(json.dumps(r['initial'], sort_keys=True).encode()).hexdigest()
    row = {k:v for k,v in r.items() if k not in ['trace', 'initial']}
    return row, identity, initial_hash


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--runs', type=Path, nargs='+', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--workers', type=int, default=8)
    args = p.parse_args()
    assert not args.output.exists()
    reports, identities = [], []
    for root in args.runs:
        files = sorted((root / 'traces').glob('*.json.gz'))
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(audit, files, chunksize=10))
        rows = json.loads((root / 'rows.json').read_text())
        assert sorted(json.dumps(r[0], sort_keys=True) for r in results) == sorted(json.dumps(r, sort_keys=True) for r in rows)
        groups = {}
        for _, identity, fingerprint in results:
            assert groups.setdefault(identity, fingerprint) == fingerprint
        summaries = json.loads((root / 'summary.json').read_text())
        assert summaries['episodes'] == len(files)
        assert summaries['control_steps'] == 50 * len(files)
        for row in summaries['summaries']:
            keys = ['task', 'regime', 'method'] if 'regime' in row else ['task', 'config']
            matches = [r for r in rows if all(r[k] == row[k] for k in keys)]
            assert row['episodes'] == len(matches)
            for metric in ['success', 'ever_success', 'last10_success', 'final_distance'] + (['estimation_rmse_m'] if 'regime' in row else []):
                assert abs(row[metric] - np.mean([r[metric] for r in matches])) < 1e-12
        identities.append(set(groups))
        reports.append({'run': root.name, 'episodes': len(files), 'control_steps': 50*len(files),
                        'distinct_task_seed_pairs': len(groups), 'status': 'passed',
                        'protocol': json.loads((root / 'protocol.json').read_text())})
    for i, a in enumerate(identities):
        for b in identities[i+1:]:
            assert not a & b, 'Split seed overlap'
    output = {'status': 'passed', 'runs': reports,
              'episodes': sum(r['episodes'] for r in reports),
              'control_steps': sum(r['control_steps'] for r in reports),
              'checks': ['50-step registered horizon', 'full terminal and summary metrics',
                         'exact causal sensor and action reconstruction', 'filter covariance replay',
                         'shared reset states across alternatives', 'disjoint splits'],
              'scope': 'Archived trace audit; no new dynamics, no learned JEV evaluation'}
    write(args.output, output)
    print(json.dumps(output), flush=True)


if __name__ == '__main__':
    main()
