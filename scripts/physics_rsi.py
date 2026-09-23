"""One offline RSI acquisition round with equal-budget controls and fresh tests.

Simulation collection can run on a CPU-only host. Selection/update require torch.
The candidate is conventional failure-directed acquisition, not claimed novel.
"""
import argparse
import concurrent.futures
import copy
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import time
from pathlib import Path

import numpy as np
from physics_phase import (TASKS, FEATURES, NAMES, SEEDS, arrays, candidate_inputs,
                           feature_vector, frozen_baselines, metrics, prepare, worker, write)

COUNTS = dict(pool=1200, validation=180, test=300, delay=300, pilot=12)
BASE_SEEDS = dict(pilot=1010000, pool=1110000, validation=1210000, test=1310000, delay=1410000)
METHODS = ['random', 'disagreement', 'counterexample']
BUDGET = 180
STEPS = 400
BATCH = 256


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def context(index, split):
    seed = BASE_SEEDS[split] + index
    rng = np.random.default_rng(seed)
    task = TASKS[index % 2]
    long = split == 'delay' or (split in ['pool', 'validation', 'pilot'] and (index // 2) % 2 == 1)
    return dict(seed=seed, index=index, split=split, task=task,
                target_stage=(index // 2) % (3 if task == TASKS[0] else 5),
                extra_ticks=int(rng.integers(0, 6)), age=int(rng.integers(0, 16)),
                delay=int(rng.integers(21, 36) if long else rng.integers(2, 21)),
                noise_std=float(rng.uniform(.001, .040)), time_price=float(rng.uniform(.02, .15)))


def prefix_worker(items):
    import gymnasium as gym
    import gymnasium_robotics
    gym.register_envs(gymnasium_robotics)
    envs = {task: gym.make(task, max_episode_steps=300) for task in TASKS}
    rows = []
    try:
        for c in items:
            snap = prepare(envs[c['task']], c)
            rows.append(dict(context=c, x=feature_vector(c, snap), stage=snap['controller'].stage,
                             stage_reached=snap['stage_reached'], state_sha256=snap['sha256']))
    finally:
        for env in envs.values():
            env.close()
    return rows


def collect(kind, root, workers):
    target = root / (kind + '.json')
    assert not target.exists(), 'Do not overwrite a collected split'
    if kind in ['test', 'delay']:
        frozen = read(root / 'frozen_protocol.json')
        assert frozen['execution_commit'] == checkout_commit()
    if kind == 'acquired':
        pool, selection = read(root / 'pool.json'), read(root / 'selection.json')
        assert digest(root / 'pool.json') == selection['pool_sha256']
        indices = sorted(set(i for ids in selection['indices'].values() for i in ids))
        contexts = [pool[i]['context'] for i in indices]
    else:
        contexts = [context(i, kind) for i in range(COUNTS[kind])]
    trace_dir = root / 'traces'
    trace_dir.mkdir(exist_ok=True)
    items = contexts if kind == 'pool' else [(c, str(trace_dir)) for c in contexts]
    rows = []
    start = time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        for batch in executor.map(prefix_worker if kind == 'pool' else worker,
                                  [items[i:i+10] for i in range(0, len(items), 10)]):
            rows.extend(batch)
            status = dict(event='collected', split=kind, count=len(rows), total=len(items),
                          elapsed_s=time.perf_counter()-start)
            write(root / 'collection_progress.json', status)
            print(json.dumps(status), flush=True)
    if kind == 'acquired':
        for row in rows:
            original = pool[row['context']['index']]
            assert row['state_sha256'] == original['state_sha256']
            np.testing.assert_array_equal(row['x'], original['x'])
    write(target, rows)
    return rows


def network(device):
    from torch import nn
    return nn.Sequential(nn.Linear(32, 64), nn.Tanh(), nn.Linear(64, 64),
                         nn.Tanh(), nn.Linear(64, 2)).to(device)


def device():
    import torch
    torch.set_num_threads(2)
    return 'cuda' if torch.cuda.is_available() else 'cpu'


def fit(train, validation, seed, initial=None):
    import torch
    dev = device()
    torch.manual_seed(seed)
    x, y, duration, _ = arrays(train)
    xv, _, _, cv = arrays(validation)
    mean = np.asarray(initial['mean']) if initial else x.mean(0)
    scale = np.asarray(initial['scale']) if initial else np.maximum(x.std(0), 1e-5)
    tx = torch.tensor(candidate_inputs(x, mean, scale, []), device=dev)
    vx = torch.tensor(candidate_inputs(xv, mean, scale, []), device=dev)
    ty = torch.tensor(y, device=dev)
    td = torch.tensor(duration / 6, device=dev)
    net = network(dev)
    if initial:
        net.load_state_dict(initial['state_dict'])
    optimizer = torch.optim.Adam(net.parameters(), lr=.002)
    best, best_step, state, curve = float('inf'), 0, None, []
    for step in range(STEPS + 1):
        if step:
            ix = torch.randint(len(x), (BATCH,), device=dev)
            p = net(tx[ix])
            loss = (torch.nn.functional.binary_cross_entropy_with_logits(p[..., 0], ty[ix])
                    + torch.nn.functional.mse_loss(p[..., 1].sigmoid(), td[ix]))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        if step % 10 == 0:
            with torch.no_grad():
                p = net(vx).sigmoid().cpu().numpy()
            a = (1-p[..., 0] + xv[:, 4, None]*6*p[..., 1]).argmin(1)
            cost = float(cv[np.arange(len(xv)), a].mean())
            curve.append(dict(step=step, validation_cost=cost,
                              train_loss=float(loss.detach()) if step else None))
            if cost < best:
                best, best_step = cost, step
                state = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
    return dict(state_dict=state, mean=mean.tolist(), scale=scale.tolist(), mask=[], feature_names=FEATURES), dict(
        seed=seed, selected_step=best_step, validation_cost=best, curve=curve,
        updates=STEPS, batch_contexts=BATCH, training_contexts=len(train))


def predict(bundle, x):
    import torch
    dev = device()
    net = network(dev)
    net.load_state_dict(bundle['state_dict'])
    with torch.no_grad():
        pred = net(torch.tensor(candidate_inputs(np.asarray(x), np.asarray(bundle['mean']),
                   np.asarray(bundle['scale']), []), device=dev)).sigmoid().cpu().numpy()
    costs = 1-pred[..., 0] + np.asarray(x)[:, 4, None]*6*pred[..., 1]
    return costs


def load_bundle(path):
    import torch
    return torch.load(path, map_location='cpu', weights_only=True)


def folds(rows):
    assignment = np.zeros(len(rows), dtype=int)
    rng = np.random.default_rng(35091)
    for task in TASKS:
        for stage in range(5):
            ix = [i for i, r in enumerate(rows) if r['context']['task'] == task and r['stage'] == stage]
            rng.shuffle(ix)
            assignment[ix] = np.arange(len(ix)) % 3
    return assignment


def knn_regret(train_x, regret, pool_x):
    mean, scale = train_x.mean(0), np.maximum(train_x.std(0), 1e-5)
    a, b = (train_x-mean)/scale, (pool_x-mean)/scale
    scores = []
    for row, z in zip(pool_x, b):
        ix = np.flatnonzero(train_x[:, 0] == row[0])
        distances = np.mean((a[ix]-z)**2, axis=1)
        nearest = np.argsort(distances, kind='stable')[:15]
        weight = 1/(.25+distances[nearest])
        scores.append(float(np.average(regret[ix[nearest]], weights=weight)))
    return np.asarray(scores)


def select_indices(x, score, method, budget=BUDGET):
    assert budget % 4 == 0
    rng = np.random.default_rng(20260923)
    result = []
    for task in [0, 1]:
        for long in [False, True]:
            group = np.flatnonzero((x[:, 0] == task) & ((x[:, 3] > .8) == long))
            shuffled = rng.permutation(group)
            n = budget // 4
            assert len(group) >= n
            if method == 'random':
                selected = shuffled[:n]
            else:
                # Identical 20% uniform exploration for both targeted methods.
                top = shuffled[np.argsort(-score[shuffled], kind='stable')[:int(n*.8)]]
                remaining = [i for i in shuffled if i not in set(top)]
                selected = np.r_[top, remaining[:n-len(top)]]
            result.extend(int(i) for i in selected)
    return sorted(result)


def select(root, base):
    import torch
    assert not (root / 'selection.json').exists()
    train, val, pool = read(base/'train.json'), read(base/'validation.json'), read(root/'pool.json')
    assert all(not {'cost', 'success', 'duration'} & r.keys() for r in pool)
    xt, _, _, ct = arrays(train)
    xp = np.asarray([r['x'] for r in pool], dtype=np.float32)
    assignment = folds(train)
    oof = np.zeros((len(SEEDS), len(train), 3), dtype=np.float32)
    trials = []
    for fold in range(3):
        fit_rows = [r for i, r in enumerate(train) if assignment[i] != fold]
        held = np.flatnonzero(assignment == fold)
        for j, seed in enumerate(SEEDS):
            bundle, trial = fit(fit_rows, val, 1000+seed)
            oof[j, held] = predict(bundle, xt[held])
            name = f'oof_{fold}_{seed}'
            torch.save(bundle, root/(name+'.pt'))
            trials.append(dict(method=name, **trial))
            print(json.dumps(dict(event='crossfit', fold=fold, seed=seed)), flush=True)
    choices = oof.argmin(2)
    regret = np.mean([ct[np.arange(len(train)), a]-ct.min(1) for a in choices], axis=0)
    error_score = knn_regret(xt, regret, xp)
    base_protocol = read(base/'frozen_protocol.json')
    prediction = []
    for seed in SEEDS:
        name = f'full_{seed}.pt'
        assert digest(base/name) == base_protocol['checkpoints'][name]
        prediction.append(predict(load_bundle(base/name), xp))
    prediction = np.asarray(prediction)
    votes = prediction.argmin(2)
    probs = np.stack([(votes == a).mean(0) for a in range(3)], axis=1)
    entropy = -(probs*np.log(np.maximum(probs, 1e-8))).sum(1)
    disagreement = entropy + prediction.std(0).mean(1)
    scores = dict(random=np.zeros(len(pool)), disagreement=disagreement, counterexample=error_score)
    selection = dict(execution_commit=checkout_commit(), pool_sha256=digest(root/'pool.json'),
                     base_train_sha256=digest(base/'train.json'), budget_per_method=BUDGET,
                     primary='counterexample minus random, equal mixture of fresh IID and long-delay contexts',
                     indices={k: select_indices(xp, v, k) for k, v in scores.items()},
                     scores={k: v.tolist() for k, v in scores.items()},
                     description='15 same-task neighbors of cross-fitted regret; 20% uniform exploration; task/delay balanced')
    write(root/'oof.json', dict(folds=assignment.tolist(), estimated_costs=oof.tolist(),
                               regrets=regret.tolist(), choices=choices.tolist()))
    write(root/'selection_trials.json', trials)
    write(root/'selection.json', selection)


def update(root, base):
    import torch
    assert not any((root/f).exists() for f in ['frozen_protocol.json', 'test.json', 'delay.json'])
    train, val = read(base/'train.json'), read(root/'validation.json')
    acquired, selection = read(root/'acquired.json'), read(root/'selection.json')
    lookup = {r['context']['index']: r for r in acquired}
    trials, checkpoint_names = [], []
    for method in ['replay_only', *METHODS]:
        selected = [] if method == 'replay_only' else [lookup[i] for i in selection['indices'][method]]
        for seed in SEEDS:
            initial = load_bundle(base/f'full_{seed}.pt')
            bundle, trial = fit(train+selected, val, seed, initial)
            name = f'{method}_{seed}.pt'
            torch.save(bundle, root/name)
            checkpoint_names.append(name)
            trials.append(dict(method=method, **trial))
            print(json.dumps(dict(event='updated', method=method, seed=seed, selected_step=trial['selected_step'])), flush=True)
    write(root/'update_trials.json', trials)
    frozen = dict(execution_commit=checkout_commit(), created_at=time.time(), test_not_generated_yet=True,
                  checkpoints={name:digest(root/name) for name in checkpoint_names},
                  original_checkpoints={f'full_{seed}.pt':digest(base/f'full_{seed}.pt') for seed in SEEDS},
                  rules=frozen_baselines(val), selection_sha256=digest(root/'selection.json'),
                  acquired_sha256=digest(root/'acquired.json'), validation_sha256=digest(root/'validation.json'),
                  test_counts={k:COUNTS[k] for k in ['test','delay']}, test_seed_bases=BASE_SEEDS,
                  primary='Mean cost difference, counterexample minus random, 600 independent contexts, 3 fixed seeds averaged',
                  limits='One acquisition draw; no conclusion about acquisition-seed population or visual control')
    write(root/'frozen_protocol.json', frozen)


def bootstrap(delta, primary=False):
    rng = np.random.default_rng(64027)
    sample = delta[rng.integers(0, len(delta), (4000, len(delta)))].mean(1)
    return dict(mean=float(delta.mean()), ci95=np.quantile(sample, [.025,.975]).tolist(),
                contexts=len(delta), primary=primary,
                interval_scope='Context-resampled, fixed trained seeds and one acquisition draw; secondary intervals unadjusted')


def evaluate(root, base):
    frozen = read(root/'frozen_protocol.json')
    for folder, names in [(root, frozen['checkpoints']), (base, frozen['original_checkpoints'])]:
        for name, expected in names.items():
            assert digest(folder/name) == expected
    models = {name[:-3]: load_bundle(root/name) for name in frozen['checkpoints']}
    models.update({f'frozen_{seed}':load_bundle(base/f'full_{seed}.pt') for seed in SEEDS})
    summaries, merged = [], []
    for split in ['test','delay']:
        rows = read(root/(split+'.json'))
        x, _, _, costs = arrays(rows)
        rules = frozen['rules']
        choices = {name:predict(bundle, x).argmin(1) for name, bundle in models.items()}
        choices.update({name:np.full(len(rows),a) for a,name in enumerate(NAMES)})
        choices['task_phase_lookup'] = np.asarray([rules['task_phase_lookup'][r['context']['task']+':'+str(r['stage'])] for r in rows])
        choices['oracle_infeasible'] = costs.argmin(1)
        write(root/(split+'_decisions.json'), {k:v.tolist() for k,v in choices.items()})
        summaries.append(dict(split=split, methods=metrics(rows, choices)))
        for i,r in enumerate(rows):
            means = {method:float(np.mean([costs[i, choices[f'{method}_{s}'][i]] for s in SEEDS]))
                     for method in ['frozen','replay_only',*METHODS]}
            merged.append(dict(split=split, task=r['context']['task'], costs=means))
    contrasts = []
    for split in ['all','test','delay']:
        for task in ['all',*TASKS]:
            rows = [r for r in merged if (split=='all' or r['split']==split) and (task=='all' or r['task']==task)]
            for reference in ['random','disagreement','replay_only','frozen']:
                delta = np.asarray([r['costs']['counterexample']-r['costs'][reference] for r in rows])
                contrasts.append(dict(split=split, task=task, reference=reference,
                                      **bootstrap(delta, split=='all' and task=='all' and reference=='random')))
    result = dict(scope=__doc__, summaries=summaries, paired_contrasts=contrasts,
                  primary=next(r for r in contrasts if r['primary']),
                  label_budget_per_method=3*BUDGET, unique_acquired_contexts=len(read(root/'acquired.json')),
                  training_trials=dict(crossfit=9, update=12),
                  shared_prefix_contexts=COUNTS['pool'], common_validation_contexts=COUNTS['validation'],
                  evaluation_contexts=COUNTS['test']+COUNTS['delay'])
    write(root/'results.json', result)
    print(json.dumps(result['primary']), flush=True)


def checkout_commit():
    cwd = Path(__file__).resolve().parents[1]
    if subprocess.check_output(['git','status','--porcelain'], cwd=cwd).strip():
        raise RuntimeError('Execution checkout must be clean')
    return subprocess.check_output(['git','rev-parse','HEAD'], cwd=cwd).decode().strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', required=True, choices=['pool','validation','pilot','select','acquired','update','test','delay','evaluate'])
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--base', type=Path)
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    commit = checkout_commit()
    args.run.mkdir(parents=True, exist_ok=True)
    versions = {k:importlib.metadata.version(k) for k in ['numpy','mujoco','gymnasium','gymnasium-robotics']}
    write(args.run/(args.mode+'_environment.json'), dict(python=platform.python_version(), versions=versions,
                                                       execution_commit=commit, started_at=time.time()))
    if args.mode in ['select','update','evaluate']:
        assert args.base is not None
        globals()[args.mode](args.run, args.base)
    else:
        collect(args.mode, args.run, args.workers)


if __name__ == '__main__':
    main()
