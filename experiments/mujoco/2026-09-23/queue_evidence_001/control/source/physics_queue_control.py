"""Post-hoc OOS sensor-delta control, explicitly outside the frozen pilot gate.

Constant additive bias cancels in the fast sensor's temporal difference.
This diagnostic quantifies that simple estimator before training any router.
"""
import argparse
import concurrent.futures
import gzip
import hashlib
import json
import subprocess
import time
from pathlib import Path

import gymnasium as gym
import gymnasium_robotics
import numpy as np
from physics_phase import TASKS, prepare, sensor_bias, write
from physics_queue_evidence import audit_prefix, branch, commands, streams


def compensated_streams(c, obs, history, grips):
    candidates, sample = streams(c, obs, history, grips)
    past_fast = history[sample] + c['noise_std'] * sensor_bias(c)
    corrected = candidates[1] + (candidates[0] - past_fast)
    # Only a label-side algebraic audit; the estimator above uses sensor samples.
    reference = history[-1] + .001 * sensor_bias(c)
    assert np.max(np.abs(corrected - reference)) < 1e-12
    return candidates + [corrected], sample


def worker(items):
    gym.register_envs(gymnasium_robotics)
    envs = {t: gym.make(t, max_episode_steps=300) for t in TASKS}
    rows = []
    for path, out in items:
        with gzip.open(path, 'rt') as f:
            original = json.load(f)
        c = original['context']
        env = envs[c['task']]
        snap = prepare(env, c)
        assert snap['sha256'] == original['snapshot']['sha256']
        variants = []
        for qi, old in enumerate(original['variants']):
            queue = commands(c, snap, qi)
            np.testing.assert_array_equal(queue, old['commands'])
            result = branch(env, c, snap, queue, 3, estimate_fn=compensated_streams)
            audit_prefix([old['branches'][0], result], queue)
            variants.append({'queue_name': old['queue_name'], 'commands': queue.tolist(), 'branch': result})
            rows.append({'context': c, 'queue': old['queue_name'], 'cost': result['cost'],
                             'success': result['success'], 'duration_s': result['duration_s'],
                             'old_cost': [r['cost'] for r in old['branches']],
                             'old_success': [r['success'] for r in old['branches']]})
        with gzip.open(Path(out) / Path(path).name, 'wt') as f:
            json.dump({'context': c, 'variants': variants}, f, allow_nan=False)
    for env in envs.values():
        env.close()
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--pilot', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    assert not subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()
    args.output.mkdir(parents=True, exist_ok=False)
    folder = args.output / 'traces'
    folder.mkdir()
    paths = sorted((args.pilot / 'traces').glob('pilot_*.json.gz'))
    assert len(paths) == 90
    inputs = {'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  'pilot_protocol_sha256': hashlib.sha256((args.pilot / 'protocol.json').read_bytes()).hexdigest(),
                  'protocol': 'post-hoc diagnostic; no retraining or independent test claim',
                  'rule': 'precise_old + fast_current - fast_at_precise_timestamp',
                  'constant_bias_cancellation': 'exact up to rounding in this synthetic sensor model',
                  'input_traces': [{'path': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]}
    write(args.output / 'protocol.json', inputs)
    items = [(str(p), str(folder)) for p in paths]
    started = time.perf_counter()
    rows = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=8) as pool:
        for batch in pool.map(worker, [items[i:i+5] for i in range(0, len(items), 5)]):
            rows.extend(batch)
    write(args.output / 'rows.json', rows)
    diffs = np.asarray([r['cost'] - r['old_cost'][1] for r in rows]).reshape(90, 3).mean(1)
    rng = np.random.default_rng(7623)
    means = diffs[rng.integers(90, size=(4000, 90))].mean(1)
    summary = {'parents': 90, 'new_branches': 270, 'success_rate': float(np.mean([r['success'] for r in rows])),
                   'mean_cost': float(np.mean([r['cost'] for r in rows])),
                   'difference_to_precise_delayed': float(diffs.mean()),
                   'difference_parent_bootstrap_95': np.quantile(means, [.025, .975]).tolist(),
                   'wall_s': time.perf_counter() - started,
                   'limitation': 'post-hoc control on development pilot; static additive sensor bias; no holdout evidence'}
    write(args.output / 'summary.json', summary)
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
