"""Audit all paired physics records; export inference-only metrics and replays."""
import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np


def read(p):
    return json.loads(p.read_text())


def paired_interval(values, seed=1729):
    rng = np.random.default_rng(seed)
    samples = values[rng.integers(len(values), size=(4000, len(values)))].mean(1)
    return dict(mean=float(values.mean()), ci95=np.quantile(samples, [.025, .975]).tolist())


def audit(root, output):
    from physics_phase import FEATURES, TASKS, SEEDS, MASKS
    output.mkdir(parents=True, exist_ok=False)
    protocol = read(root / 'frozen_protocol.json')
    for name, expected in protocol['checkpoints'].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
    seen, counts, checks = set(), {}, 0
    for split in ['train', 'validation', 'test', 'delay']:
        rows = read(root / (split + '.json'))
        seeds = {r['context']['seed'] for r in rows}
        assert not seen.intersection(seeds)
        assert len(seeds) == len(rows)
        seen.update(seeds)
        counts[split] = dict(contexts=len(rows), unreached=sum(not r['stage_reached'] for r in rows),
                             stages=dict(collections.Counter(r['context']['task'] + ':' + str(r['stage']) for r in rows)))
        for r in rows:
            assert len(r['x']) == len(FEATURES)
            with gzip.open(root / 'traces' / f"{split}_{r['context']['index']:05d}.json.gz", 'rt') as f:
                rec = json.load(f)
            state = np.asarray(rec['snapshot']['state'], dtype=np.float64)
            assert hashlib.sha256(state.tobytes()).hexdigest() == r['state_sha256']
            for a, b in enumerate(rec['branches']):
                assert b['state_sha256'] == r['state_sha256']
                streak = 0
                for k, step in enumerate(b['trace']):
                    assert abs(step['t'] - (k + 1) * .04) < 1e-9
                    assert np.isfinite(step['qpos']).all() and np.isfinite(step['qvel']).all()
                    assert np.max(np.abs(step['action'])) <= 1.0
                    streak = streak + 1 if step['success'] else 0
                assert (streak >= 10) == b['success'] == r['success'][a]
                assert abs(b['duration_s'] - len(b['trace']) * .04) < 1e-9
                expected = float(not b['success']) + r['context']['time_price'] * b['duration_s']
                assert abs(expected - r['cost'][a]) < 1e-9
                checks += 1
    contrasts = []
    means = []
    for split in ['test', 'delay']:
        rows = read(root / (split + '.json'))
        d = read(root / (split + '_decisions.json'))
        costs = np.asarray([r['cost'] for r in rows])
        successes = np.asarray([r['success'] for r in rows])
        durations = np.asarray([r['duration'] for r in rows])
        values = {k: costs[np.arange(len(rows)), v] for k, v in d['choices'].items()}
        for variant in MASKS:
            values[variant + '_mean'] = np.mean([values[f'{variant}_{s}'] for s in SEEDS], axis=0)
        for task in TASKS:
            ix = np.asarray([i for i, r in enumerate(rows) if r['context']['task'] == task])
            for variant in MASKS:
                choices = np.asarray([d['choices'][f'{variant}_{s}'] for s in SEEDS])[:, ix]
                means.append(dict(split=split, task=task, method=variant,
                                  contexts=len(ix), mean_cost=float(values[variant + '_mean'][ix].mean()),
                                  success_rate=float(successes[ix[None, :], choices].mean()),
                                  duration_s=float(durations[ix[None, :], choices].mean())))
            for reference in ['continue', 'stop_refresh', 'async_refresh', 'task_phase_lookup',
                              'age_noise_rule', 'no_phase_mean', 'no_age_mean', 'no_history_mean']:
                contrasts.append(dict(split=split, task=task, comparison='full_mean minus ' + reference,
                                      **paired_interval((values['full_mean'] - values[reference])[ix])))
    result = dict(scope='post-hoc paired audit; context bootstrap; no multiple-comparison correction; '
                         'training-seed population uncertainty is not estimated', branch_checks=checks,
                  counts=counts, feature_names=FEATURES, variant_means=means, paired_cost_differences=contrasts)
    (output / 'audit.json').write_text(json.dumps(result, indent=2))
    return result


def replay(root, output):
    import gymnasium as gym
    import gymnasium_robotics
    import imageio.v2 as imageio
    from physics_phase import branch, prepare, NAMES
    gym.register_envs(gymnasium_robotics)
    reports = []
    # First indices for approach/contact on both tasks, and pick transport.
    # All candidates are shown; outcomes are never used to pick these cases.
    for split in ['test', 'delay']:
        rows = read(root / (split + '.json'))
        for index in [0, 1, 4, 5, 9]:
            r = rows[index]
            env = gym.make(r['context']['task'], max_episode_steps=300,
                           render_mode='rgb_array', width=640, height=480)
            snap = prepare(env, r['context'])
            assert snap['sha256'] == r['state_sha256']
            with gzip.open(root / 'traces' / f'{split}_{index:05d}.json.gz', 'rt') as f:
                original = json.load(f)
            for a, name in enumerate(NAMES):
                stem = f'{split}_{index}_{name}'
                with imageio.get_writer(output / (stem + '.mp4'), fps=25) as writer:
                    rec = branch(env, r['context'], snap, a, writer=writer)
                exact = rec == original['branches'][a]
                reports.append(dict(split=split, index=index, choice=a, name=name, exact_trace_match=exact,
                                    success=rec['success'], duration_s=rec['duration_s'], stem=stem))
                assert exact, stem
            with gzip.open(output / f'{split}_{index}.json.gz', 'wt') as f:
                json.dump(original, f)
            env.close()
    (output / 'replays.json').write_text(json.dumps(reports, indent=2))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--video', action='store_true')
    args = p.parse_args()
    result = audit(args.run, args.output)
    print(json.dumps(dict(branch_checks=result['branch_checks'], counts=result['counts'])), flush=True)
    if args.video:
        replay(args.run, args.output)
        print('30 exact-trace render replays passed', flush=True)


if __name__ == '__main__':
    main()
