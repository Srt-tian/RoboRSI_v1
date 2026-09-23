"""Mechanism pilot: route delayed evidence after a shared committed prefix.

No robot I/O, GPT, images, foundation model, or trainable action generator.
All route branches of a queue execute exactly the same immutable commands.
The decision is made before that prefix and persists for the remaining rollout.
"""
import argparse
import concurrent.futures
import copy
import gzip
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

os.environ.setdefault('MUJOCO_GL', 'egl')
import gymnasium as gym
import gymnasium_robotics
import mujoco
import numpy as np
from physics_phase import TASKS, prepare, restore, sensor_bias, write

ROUTES = ['fast_current', 'precise_delayed', 'grip_transported']
QUEUES = ['hold', 'half_proposal', 'proposal']
MAX_QUEUE = 12
BASE_FEATURES = ['pick_task', *['stage_' + str(i) for i in range(5)],
                 'noise_std', 'actual_precise_age_s', 'time_price',
                 *['goal_grip_' + d for d in 'xyz'],
                 *['fast_grip_' + d for d in 'xyz'],
                 *['precise_grip_' + d for d in 'xyz'],
                 *['grip_motion_since_precise_' + d for d in 'xyz'],
                 'finger_left', 'finger_right', 'last_opening',
                 *['recent_grip_motion_' + d for d in 'xyz']]
QUEUE_FEATURES = ['queue_steps', *[f'queue_{i}_{d}' for i in range(MAX_QUEUE)
                                  for d in ['x', 'y', 'z', 'gripper']]]
FEATURES = BASE_FEATURES + QUEUE_FEATURES
SPLIT_SEEDS = {'pilot': 1510000, 'train': 1610000, 'validation': 1710000,
                   'test': 1810000, 'delay': 1910000}


def context(index, split):
    seed = SPLIT_SEEDS[split] + index
    rng = np.random.default_rng(seed)
    task = TASKS[index % 2]
    return {'seed': seed, 'index': index, 'split': split, 'task': task,
                'target_stage': (index // 2) % (3 if task == TASKS[0] else 5),
                'extra_ticks': int(rng.integers(0, 6)), 'age': 0,
                'delay': int(rng.integers(2, 21) if split != 'delay' else rng.integers(21, 36)),
                'queue_steps': int(rng.choice([4, 8, 12])),
                'noise_std': float(rng.uniform(.001, .040)),
                'time_price': float(rng.uniform(.02, .15))}


def streams(c, obs, history, grips):
    current = len(history) - 1
    sample = max(0, current - c['delay'])
    b = sensor_bias(c)
    fast = history[current] + c['noise_std'] * b
    precise = history[sample] + .001 * b
    transported = precise + obs['observation'][:3] - grips[sample]
    return [fast, precise, transported], sample


def commands(c, snap, queue_kind):
    fast = streams(c, snap['obs'], snap['history'], snap['grips'])[0][0]
    ctrl = copy.deepcopy(snap['controller'])
    action = ctrl.action(snap['obs']['observation'][:3], fast,
                         snap['obs']['desired_goal'])
    # Only the XYZ command differs; gripper command and duration are matched.
    action[:3] *= [0.0, 0.5, 1.0][queue_kind]
    return np.tile(action, (c['queue_steps'], 1))


def feature_vector(c, snap, queue):
    obs = snap['obs']
    grip = obs['observation'][:3]
    estimates, sample = streams(c, obs, snap['history'], snap['grips'])
    last_opening = (snap['actions'][-1][3] if snap['actions'] else
                    (1.0 if c['task'] == TASKS[1] else -1.0))
    x = [float(c['task'] == TASKS[1]), *np.eye(5)[snap['controller'].stage],
         c['noise_std'], (len(snap['history']) - 1 - sample) * .04, c['time_price'],
         *(obs['desired_goal'] - grip), *(estimates[0] - grip), *(estimates[1] - grip),
         *(grip - snap['grips'][sample]), *obs['observation'][9:11], last_opening,
         *(grip - snap['grips'][max(0, len(snap['grips']) - 6)])]
    assert len(x) == len(BASE_FEATURES)
    padded = np.zeros((MAX_QUEUE, 4))
    padded[:len(queue)] = queue
    x.extend([len(queue), *padded.ravel()])
    assert len(x) == len(FEATURES)
    return list(map(float, x))


def branch(env, c, snap, queue, route, estimate_fn=None):
    obs, ctrl, history = restore(env, snap)
    grips = copy.deepcopy(snap['grips'])
    estimate_fn = streams if estimate_fn is None else estimate_fn
    trace, streak = [], 0
    for k in range(150):
        estimates, sample = estimate_fn(c, obs, history, grips)
        locked = k < len(queue)
        perceived = estimates[0 if locked else route]
        # Controller bookkeeping sees the same fast stream during the prefix.
        proposed = ctrl.action(obs['observation'][:3], perceived, obs['desired_goal'])
        action = queue[k].copy() if locked else proposed
        obs, _, terminated, truncated, info = env.step(action)
        history.append(obs['observation'][3:6].copy())
        grips.append(obs['observation'][:3].copy())
        success = bool(info['is_success'])
        streak = streak + 1 if success else 0
        trace.append({'step': k + 1, 't': (k + 1) * .04, 'locked': locked,
                          'stage': ctrl.stage, 'action': action.tolist(),
                          'qpos': env.unwrapped.data.qpos.tolist(),
                          'qvel': env.unwrapped.data.qvel.tolist(),
                          'grip': obs['observation'][:3].tolist(),
                          'object': obs['achieved_goal'].tolist(), 'goal': obs['desired_goal'].tolist(),
                          'observed_object': perceived.tolist(),
                          'precise_sample_age_s': (len(history) - 2 - sample) * .04,
                          'contacts': int(env.unwrapped.data.ncon), 'success': success})
        # Never end before the prefix is completely consumed.
        if (streak >= 10 and k + 1 >= len(queue)) or terminated or truncated:
            break
    success = streak >= 10
    duration = len(trace) * .04
    return {'success': success, 'duration_s': duration,
                'cost': float(not success) + c['time_price'] * duration,
                'state_sha256': snap['sha256'], 'trace': trace}


def audit_prefix(branches, queue):
    base = branches[0]['trace'][:len(queue)]
    assert len(base) == len(queue)
    for b in branches[1:]:
        assert b['trace'][:len(queue)] == base, 'route leaked into locked prefix'
    for k, row in enumerate(base):
        assert np.array_equal(row['action'], queue[k])
    return hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()


def worker(items):
    gym.register_envs(gymnasium_robotics)
    envs = {t: gym.make(t, max_episode_steps=300) for t in TASKS}
    rows = []
    for c, folder in items:
        env = envs[c['task']]
        snap = prepare(env, c)
        variants = []
        for qi, name in enumerate(QUEUES):
            queue = commands(c, snap, qi)
            branches = [branch(env, c, snap, queue, r) for r in range(len(ROUTES))]
            prefix_sha = audit_prefix(branches, queue)
            variants.append({'queue_name': name, 'commands': queue.tolist(),
                                 'prefix_sha256': prefix_sha, 'branches': branches})
            rows.append({'context': c, 'queue': name, 'x': feature_vector(c, snap, queue),
                             'stage': snap['controller'].stage, 'stage_reached': snap['stage_reached'],
                             'state_sha256': snap['sha256'], 'prefix_sha256': prefix_sha,
                             'success': [b['success'] for b in branches],
                             'duration': [b['duration_s'] for b in branches],
                             'cost': [b['cost'] for b in branches]})
        record = {'context': c, 'snapshot': {'sha256': snap['sha256'],
                      'state': snap['integration_state'].tolist(), 'controller': vars(snap['controller']),
                      'prefix_object': [p.tolist() for p in snap['history']],
                      'prefix_grip': [p.tolist() for p in snap['grips']],
                      'prefix_actions': [p.tolist() for p in snap['actions']]}, 'variants': variants}
        with gzip.open(Path(folder) / f"{c['split']}_{c['index']:05d}.json.gz", 'wt') as f:
            json.dump(record, f, allow_nan=False)
    for env in envs.values():
        env.close()
    return rows


def mechanism_summary(rows):
    by_parent = {}
    for r in rows:
        by_parent.setdefault(r['context']['seed'], []).append(r)
    # An optimistic lower bound: each parent may choose its own best fixed route,
    # but that route must be shared over the three queue interventions.
    pairs = []
    for seed, group in sorted(by_parent.items()):
        assert len(group) == len(QUEUES)
        assert len({g['state_sha256'] for g in group}) == 1
        assert all(g['x'][:len(BASE_FEATURES)] == group[0]['x'][:len(BASE_FEATURES)] for g in group)
        cost = np.asarray([r['cost'] for r in group])
        best = cost.min(1)
        regret = cost - best[:, None]
        gap = float(cost.mean(0).min() - best.mean())
        # Exclude ties: no one route is within .02 cost of optimal in every queue.
        material_flip = not bool(np.any(np.all(regret <= .02, axis=0)))
        pairs.append({'seed': seed, 'task': group[0]['context']['task'],
                          'queue_blind_oracle_gap': gap, 'material_flip': material_flip,
                          'choices': cost.argmin(1).tolist(), 'costs': cost.tolist()})
    all_cost = np.asarray([r['cost'] for r in rows])
    all_success = np.asarray([r['success'] for r in rows])
    gaps = np.asarray([p['queue_blind_oracle_gap'] for p in pairs])
    rng = np.random.default_rng(6721)
    means = gaps[rng.integers(len(gaps), size=(4000, len(gaps)))].mean(1)
    flips = sum(p['material_flip'] for p in pairs)
    result = {'parent_contexts': len(pairs), 'queue_contexts': len(rows), 'branches': len(rows) * 3,
                  'scope': 'mechanism pilot; post-outcome oracles are not executable policies',
                  'route_cost': dict(zip(ROUTES, all_cost.mean(0).tolist())),
                  'route_success': dict(zip(ROUTES, all_success.mean(0).tolist())),
                  'oracle_cost': float(all_cost.min(1).mean()),
                  'queue_blind_oracle_gap': float(gaps.mean()),
                  'gap_parent_bootstrap_95': np.quantile(means, [.025, .975]).tolist(),
                  'material_flip_parents': flips, 'pairs': pairs}
    result['pilot_gate_passed'] = bool(gaps.mean() >= .005 and flips >= 10)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--split', choices=SPLIT_SEEDS, default='pilot')
    p.add_argument('--parents', type=int, default=90)
    p.add_argument('--workers', type=int, default=8)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    folder = args.output / 'traces'
    folder.mkdir()
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()
    assert not dirty, 'commit source before collecting'
    write(args.output / 'protocol.json', {'source_commit': commit, 'split': args.split,
          'parents': args.parents, 'workers': args.workers, 'routes': ROUTES, 'queues': QUEUES,
          'features': FEATURES, 'control_dt_s': .04, 'physics_dt_s': .002,
          'decision': 'one route chosen before committed prefix, held until termination',
          'environment': {'mujoco': mujoco.__version__, 'gymnasium': gym.__version__,
                           'gymnasium_robotics': gymnasium_robotics.__version__},
          'pilot_gate': {'mean_queue_blind_oracle_gap': .005, 'min_material_flip_parents': 10,
                          'material_regret': .02}, 'created_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    items = [(context(i, args.split), str(folder)) for i in range(args.parents)]
    rows = []
    started = time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        for batch in pool.map(worker, [items[i:i+5] for i in range(0, len(items), 5)]):
            rows.extend(batch)
            print(json.dumps({'event': 'collected', 'parents': len(rows) // 3,
                                  'total': args.parents}), flush=True)
    write(args.output / 'rows.json', rows)
    summary = mechanism_summary(rows)
    summary['wall_s'] = time.perf_counter() - started
    write(args.output / 'summary.json', summary)
    print(json.dumps({k: v for k, v in summary.items() if k != 'pairs'}), flush=True)


if __name__ == '__main__':
    main()
