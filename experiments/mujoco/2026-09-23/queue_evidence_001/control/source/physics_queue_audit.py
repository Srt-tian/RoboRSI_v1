"""Audit every branch, including reconstructing its causal sensor inputs."""
import argparse
import gzip
import json
from pathlib import Path

import numpy as np
from physics_queue_evidence import audit_prefix, context, sensor_bias


def audit_branch(c, snap, queue, result, route):
    history = [np.asarray(x) for x in snap['prefix_object']]
    grips = [np.asarray(x) for x in snap['prefix_grip']]
    bias = sensor_bias(c)
    trace = result['trace']
    for k, s in enumerate(trace):
        assert s['step'] == k + 1 and s['t'] == (k + 1) * .04
        assert s['locked'] == (k < len(queue))
        assert np.isfinite(s['qpos']).all() and np.isfinite(s['qvel']).all()
        assert len(s['action']) == 4 and np.max(np.abs(s['action'])) <= 1
        sample = max(0, len(history) - 1 - c['delay'])
        fast = history[-1] + c['noise_std'] * bias
        precise = history[sample] + .001 * bias
        transport = precise + grips[-1] - grips[sample]
        delta = precise + fast - (history[sample] + c['noise_std'] * bias)
        expected = [fast, precise, transport, delta][0 if s['locked'] else route]
        np.testing.assert_allclose(expected, s['observed_object'], rtol=0, atol=5e-15)
        assert s['precise_sample_age_s'] == (len(history) - 1 - sample) * .04
        history.append(np.asarray(s['object']))
        grips.append(np.asarray(s['grip']))
    assert 10 <= len(trace) <= 150
    assert result['success'] == all(s['success'] for s in trace[-10:])
    assert result['duration_s'] == len(trace) * .04
    assert abs(result['cost'] - (float(not result['success']) + c['time_price'] * len(trace) * .04)) < 1e-12


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--pilot', type=Path, required=True)
    p.add_argument('--control', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    n, steps = 0, 0
    paths = sorted((args.pilot / 'traces').glob('pilot_*.json.gz'))
    assert len(paths) == 90
    for i, path in enumerate(paths):
        with gzip.open(path, 'rt') as f:
            record = json.load(f)
        with gzip.open(args.control / 'traces' / path.name, 'rt') as f:
            control = json.load(f)
        c, snap = record['context'], record['snapshot']
        assert c == context(i, 'pilot') == control['context']
        for old, extra in zip(record['variants'], control['variants']):
            queue = np.asarray(old['commands'])
            np.testing.assert_array_equal(queue, extra['commands'])
            branches = old['branches'] + [extra['branch']]
            audit_prefix(branches, queue)
            for route, result in enumerate(branches):
                assert result['state_sha256'] == snap['sha256']
                audit_branch(c, snap, queue, result, route)
                n += 1
                steps += len(result['trace'])
    result = {'parents': 90, 'branches': n, 'steps': steps, 'all_passed': True,
                  'checks': ['exact common prefix', 'seed protocol', 'causal sensor reconstruction',
                          'finite states', 'bounded actions', 'success and cost accounting']}
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
