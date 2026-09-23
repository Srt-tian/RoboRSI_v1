"""Paired mid-skill information decisions in MuJoCo, without GPT or official Jev.

Clean scripted prefixes form a controlled checkpoint curriculum. After the fork,
all policies see only noisy/delayed object sensors and exact proprioception.
One typed decision per checkpoint; this is not yet a recurrent learned policy.
"""
import argparse
import concurrent.futures
import copy
import gzip
import hashlib
import json
import os
import time
from pathlib import Path

os.environ.setdefault('MUJOCO_GL', 'egl')
import gymnasium as gym
import gymnasium_robotics
import mujoco
import numpy as np

from physics_skills import Controller

TASKS = ['FetchPush-v4', 'FetchPickAndPlace-v4']
NAMES = ['continue', 'stop_refresh', 'async_refresh']
FEATURES = ['pick_task', 'noise_std', 'age_s', 'delay_s', 'time_price',
            *['goal_grip_' + d for d in 'xyz'], *['observed_object_grip_' + d for d in 'xyz'],
            *['stage_' + str(i) for i in range(5)],
            *['recent_grip_motion_' + d for d in 'xyz'],
            *['recent_action_' + d for d in 'xyz'], 'last_gripper_command',
            *['proposed_action_' + d for d in 'xyz'],
            *['grip_motion_since_sample_' + d for d in 'xyz']]
SEEDS = [11, 22, 33]
MASKS = {'full': [], 'no_phase': list(range(11, 16)), 'no_age': [2],
         'no_history': list(range(16, 29))}


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False))


def context(index, split):
    seed = dict(pilot=510000, train=610000, validation=710000,
                test=810000, delay=910000)[split] + index
    rng = np.random.default_rng(seed)
    task = TASKS[index % 2]
    return dict(seed=seed, split=split, index=index, task=task,
                target_stage=(index // 2) % (3 if task == TASKS[0] else 5),
                extra_ticks=int(rng.integers(0, 6)), age=int(rng.integers(0, 16)),
                delay=int(rng.integers(2, 21) if split != 'delay' else rng.integers(21, 36)),
                noise_std=float(rng.uniform(.001, .040)), time_price=float(rng.uniform(.02, .15)))


def state_vector(env):
    spec = mujoco.mjtState.mjSTATE_INTEGRATION
    v = np.zeros(mujoco.mj_stateSize(env.unwrapped.model, spec))
    mujoco.mj_getState(env.unwrapped.model, env.unwrapped.data, v, spec)
    return v


def snapshot(env, obs, controller, history, grips, actions):
    data = mujoco.MjData(env.unwrapped.model)
    mujoco.mj_copyData(data, env.unwrapped.model, env.unwrapped.data)
    state = state_vector(env)
    return dict(data=data, obs=copy.deepcopy(obs), controller=copy.deepcopy(controller),
                elapsed=env._elapsed_steps, history=copy.deepcopy(history),
                grips=copy.deepcopy(grips), actions=copy.deepcopy(actions),
                integration_state=state, sha256=hashlib.sha256(state.tobytes()).hexdigest())


def restore(env, snap):
    mujoco.mj_copyData(env.unwrapped.data, env.unwrapped.model, snap['data'])
    env._elapsed_steps = snap['elapsed']
    assert np.array_equal(state_vector(env), snap['integration_state'])
    return copy.deepcopy(snap['obs']), copy.deepcopy(snap['controller']), copy.deepcopy(snap['history'])


def prepare(env, c):
    obs, _ = env.reset(seed=c['seed'])
    ctrl = Controller(c['task'])
    history = [obs['observation'][3:6].copy()]
    grips = [obs['observation'][:3].copy()]
    actions = []
    reached_at = None
    for k in range(90):
        if ctrl.stage == c['target_stage'] and reached_at is None:
            reached_at = k
        if reached_at is not None and k >= reached_at + c['extra_ticks']:
            break
        action = ctrl.action(obs['observation'][:3], obs['observation'][3:6], obs['desired_goal'])
        obs, _, _, _, _ = env.step(action)
        actions.append(action.copy())
        history.append(obs['observation'][3:6].copy())
        grips.append(obs['observation'][:3].copy())
    snap = snapshot(env, obs, ctrl, history, grips, actions)
    snap['stage_reached'] = reached_at is not None
    return snap


def sensor_bias(c):
    bias = np.random.default_rng(c['seed'] + 333).normal(size=3)
    bias[2] = 0
    return bias


def feature_vector(c, snap):
    age = min(c['age'], len(snap['history']) - 1)
    perceived = snap['history'][-1-age] + sensor_bias(c) * c['noise_std']
    grip = snap['obs']['observation'][:3]
    goal = snap['obs']['desired_goal']
    recent = snap['actions'][-5:]
    mean_action = np.mean(recent, axis=0) if recent else np.zeros(4)
    last_opening = recent[-1][3] if recent else (1 if c['task'] == TASKS[1] else -1)
    proposed = copy.deepcopy(snap['controller']).action(grip, perceived, goal)
    x = [float(c['task'] == TASKS[1]), c['noise_std'], age * .04, c['delay'] * .04, c['time_price'],
         *(goal - grip), *(perceived - grip), *np.eye(5)[snap['controller'].stage],
         *(grip - snap['grips'][max(0, len(snap['grips']) - 6)]),
         *mean_action[:3], last_opening, *proposed[:3], *(grip - snap['grips'][-1-age])]
    assert len(x) == len(FEATURES)
    return list(map(float, x))


def safe_render(env):
    data = mujoco.MjData(env.unwrapped.model)
    mujoco.mj_copyData(data, env.unwrapped.model, env.unwrapped.data)
    try:
        return env.render()
    finally:
        mujoco.mj_copyData(env.unwrapped.data, env.unwrapped.model, data)


def branch(env, c, snap, choice, writer=None):
    obs, ctrl, history = restore(env, snap)
    first = len(history) - 1
    bias = sensor_bias(c)
    hold_opening = feature_vector(c, snap)[22]
    trace = []
    streak = 0
    for k in range(150):
        current = len(history) - 1
        refreshed = choice != 0 and k >= c['delay']
        requested_age = c['delay'] if refreshed else c['age']
        sample_index = max(first if refreshed else 0, current - requested_age)
        perceived = history[sample_index] + bias * (.001 if refreshed else c['noise_std'])
        if choice == 1 and k < c['delay']:
            action = np.r_[np.zeros(3), hold_opening]
        else:
            action = ctrl.action(obs['observation'][:3], perceived, obs['desired_goal'])
        obs, _, terminated, truncated, info = env.step(action)
        history.append(obs['observation'][3:6].copy())
        success = bool(info['is_success'])
        streak = streak + 1 if success else 0
        trace.append(dict(step=k + 1, t=(k + 1) * .04, stage=ctrl.stage,
                          action=action.tolist(), qpos=env.unwrapped.data.qpos.tolist(),
                          qvel=env.unwrapped.data.qvel.tolist(),
                          grip=obs['observation'][:3].tolist(), object=obs['achieved_goal'].tolist(),
                          observed_object=perceived.tolist(), goal=obs['desired_goal'].tolist(),
                          contacts=int(env.unwrapped.data.ncon), sample_age_s=(current - sample_index) * .04,
                          refreshed=refreshed, waiting=choice == 1 and k < c['delay'], success=success))
        if writer is not None:
            writer.append_data(safe_render(env))
        if streak >= 10 or terminated or truncated:
            break
    success = streak >= 10
    duration = len(trace) * .04
    return dict(success=success, duration_s=duration, cost=float(not success) + c['time_price'] * duration,
                state_sha256=snap['sha256'], trace=trace)


def worker(items):
    gym.register_envs(gymnasium_robotics)
    envs = {task: gym.make(task, max_episode_steps=300) for task in TASKS}
    rows = []
    for c, folder in items:
        env = envs[c['task']]
        snap = prepare(env, c)
        branches = [branch(env, c, snap, a) for a in range(3)]
        with gzip.open(Path(folder) / f"{c['split']}_{c['index']:05d}.json.gz", 'wt') as f:
            json.dump(dict(context=c, snapshot=dict(state=snap['integration_state'].tolist(),
                          sha256=snap['sha256'], controller=vars(snap['controller']),
                          prefix_object=[p.tolist() for p in snap['history']],
                          prefix_grip=[p.tolist() for p in snap['grips']],
                          prefix_actions=[p.tolist() for p in snap['actions']]), branches=branches), f)
        rows.append(dict(context=c, x=feature_vector(c, snap), stage=snap['controller'].stage,
                         stage_reached=snap['stage_reached'], state_sha256=snap['sha256'],
                         success=[b['success'] for b in branches], duration=[b['duration_s'] for b in branches],
                         cost=[b['cost'] for b in branches]))
    for env in envs.values():
        env.close()
    return rows


def dataset(count, split, out):
    folder = out / 'traces'
    folder.mkdir(exist_ok=True)
    items = [(context(i, split), str(folder)) for i in range(count)]
    rows = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        for batch in pool.map(worker, [items[i:i+10] for i in range(0, count, 10)]):
            rows.extend(batch)
            print(json.dumps(dict(event='simulated', split=split, n=len(rows), total=count)), flush=True)
    write(out / (split + '.json'), rows)
    return rows


def arrays(rows):
    return tuple(np.asarray([r[k] for r in rows], dtype=np.float32) for k in ('x', 'success', 'duration', 'cost'))


def candidate_inputs(x, mean, scale, mask):
    z = (x - mean) / scale
    z[:, mask] = 0
    return np.concatenate([np.repeat(z[:, None, :], 3, axis=1),
                           np.broadcast_to(np.eye(3), (len(x), 3, 3))], axis=2).astype(np.float32)


def train_models(train, val, out):
    import torch
    from torch import nn
    torch.set_num_threads(2)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    xt, yt, dt, ct = arrays(train)
    xv, _, _, cv = arrays(val)
    mean, scale = xt.mean(0), np.maximum(xt.std(0), 1e-5)
    models, trials = {}, []
    for variant, mask in MASKS.items():
        tx = torch.tensor(candidate_inputs(xt, mean, scale, mask), device=device)
        vx = torch.tensor(candidate_inputs(xv, mean, scale, mask), device=device)
        ty, td = torch.tensor(yt, device=device), torch.tensor(dt / 6, device=device)
        for seed in SEEDS:
            torch.manual_seed(seed)
            net = nn.Sequential(nn.Linear(len(FEATURES) + 3, 64), nn.Tanh(),
                                nn.Linear(64, 64), nn.Tanh(), nn.Linear(64, 2)).to(device)
            optimizer = torch.optim.Adam(net.parameters(), lr=.002)
            key = f'{variant}_{seed}'
            best, curve = float('inf'), []
            for epoch in range(1, 401):
                pred = net(tx)
                loss = nn.functional.binary_cross_entropy_with_logits(pred[:, :, 0], ty) + nn.functional.mse_loss(pred[:, :, 1].sigmoid(), td)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                if epoch % 10 == 0:
                    with torch.no_grad():
                        p = net(vx).sigmoid().cpu().numpy()
                    a = (1 - p[:, :, 0] + xv[:, 4, None] * p[:, :, 1] * 6).argmin(1)
                    cost = float(cv[np.arange(len(cv)), a].mean())
                    curve.append(dict(epoch=epoch, train_loss=float(loss.detach()), validation_cost=cost))
                    if cost < best:
                        best, best_epoch = cost, epoch
                        state = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
            net.load_state_dict(state)
            torch.save(dict(state_dict=state, mean=mean.tolist(), scale=scale.tolist(), mask=mask,
                            feature_names=FEATURES), out / (key + '.pt'))
            models[key] = (net, mask)
            trials.append(dict(method=key, selected_epoch=best_epoch, validation_cost=best, curve=curve))
            print(json.dumps(dict(event='trained', method=key, validation_cost=best)), flush=True)
    write(out / 'trials.json', trials)
    return models, mean, scale, device


def frozen_baselines(val):
    x, _, _, c = arrays(val)
    fixed = int(c.mean(0).argmin())
    lookup = {}
    for task in TASKS:
        for stage in range(5):
            ix = [i for i, r in enumerate(val) if r['context']['task'] == task and r['stage'] == stage]
            lookup[task + ':' + str(stage)] = int(c[ix].mean(0).argmin()) if ix else fixed
    best = (float('inf'), None)
    for age in [0, .08, .16, .32, .48, 1]:
        for noise in [.005, .015, .025, .035, 1]:
            for choice in [1, 2]:
                a = np.where((x[:, 2] >= age) | (x[:, 1] >= noise), choice, 0)
                loss = float(c[np.arange(len(c)), a].mean())
                if loss < best[0]:
                    best = (loss, dict(age=age, noise=noise, refresh_choice=choice))
    return dict(fixed=fixed, task_phase_lookup=lookup, age_noise_rule=best[1])


def metrics(rows, choices):
    _, y, d, c = arrays(rows)
    result = {}
    for name, a in choices.items():
        result[name] = {}
        for task in ['all', *TASKS]:
            ix = np.asarray([i for i, r in enumerate(rows) if task == 'all' or r['context']['task'] == task])
            aa = a[ix]
            result[name][task] = dict(contexts=len(ix), success_rate=float(y[ix, aa].mean()),
                                    mean_cost=float(c[ix, aa].mean()), duration_s=float(d[ix, aa].mean()),
                                    oracle_regret=float((c[ix, aa] - c[ix].min(1)).mean()),
                                    choices=np.bincount(aa, minlength=3).tolist())
    return result


def evaluate(rows, models, mean, scale, device, rules, out, split):
    import torch
    x, _, _, c = arrays(rows)
    n = len(rows)
    rule = rules['age_noise_rule']
    choices = {NAMES[i]: np.full(n, i) for i in range(3)}
    choices['validation_fixed'] = np.full(n, rules['fixed'])
    choices['task_phase_lookup'] = np.asarray([rules['task_phase_lookup'][r['context']['task'] + ':' + str(r['stage'])] for r in rows])
    choices['age_noise_rule'] = np.where((x[:, 2] >= rule['age']) | (x[:, 1] >= rule['noise']), rule['refresh_choice'], 0)
    choices['oracle_infeasible'] = c.argmin(1)
    predictions = {}
    for name, (net, mask) in models.items():
        with torch.no_grad():
            p = net(torch.tensor(candidate_inputs(x, mean, scale, mask), device=device)).sigmoid().cpu().numpy()
        choices[name] = (1 - p[:, :, 0] + x[:, 4, None] * p[:, :, 1] * 6).argmin(1)
        predictions[name] = p.tolist()
    write(out / (split + '_decisions.json'), dict(choices={k: v.tolist() for k, v in choices.items()}, predictions=predictions))
    return dict(split=split, methods=metrics(rows, choices))


def qualify(out, count, start_seed):
    gym.register_envs(gymnasium_robotics)
    import physics_pilot
    physics_pilot.Controller = Controller
    rows = []
    for task in TASKS:
        env = gym.make(task, max_episode_steps=150)
        for seed in range(start_seed, start_seed + count):
            row = physics_pilot.episode(env, task, seed)
            with gzip.open(out / f'{task}_{seed}.json.gz', 'wt') as f:
                json.dump(row, f)
            rows.append({k: v for k, v in row.items() if k != 'trace'})
        env.close()
    summary = dict(scope='fixed skill qualification, privileged sensor', episodes=rows,
                   metrics={task: {key: sum(r[key] for r in rows if r['task'] == task) / count
                                   for key in ['ever_success', 'final_success', 'sustained_last10']} for task in TASKS})
    write(out / 'summary.json', summary)
    print(json.dumps(summary['metrics']), flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--mode', choices=['pilot', 'qualification', 'study'], default='pilot')
    p.add_argument('--train', type=int, default=600)
    p.add_argument('--validation', type=int, default=180)
    p.add_argument('--test', type=int, default=360)
    p.add_argument('--seeds', type=int, default=30)
    p.add_argument('--start-seed', type=int, default=2000)
    args = p.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'config.json', dict(scope=__doc__, features=FEATURES, candidates=NAMES,
                                  counts=vars(args) | {'output': str(out)}, masks=MASKS, seeds=SEEDS,
                                  source_sha256={f: hashlib.sha256(Path(__file__).with_name(f).read_bytes()).hexdigest()
                                                 for f in ['physics_phase.py', 'physics_skills.py', 'physics_pilot.py']}))
    if args.mode == 'qualification':
        qualify(out, args.seeds, args.start_seed)
        return
    if args.mode == 'pilot':
        rows = dataset(args.seeds, 'pilot', out)
        write(out / 'results.json', dict(methods=metrics(rows, {NAMES[i]: np.full(len(rows), i) for i in range(3)})))
        return
    train, val = dataset(args.train, 'train', out), dataset(args.validation, 'validation', out)
    models, mean, scale, device = train_models(train, val, out)
    rules = frozen_baselines(val)
    write(out / 'frozen_protocol.json', dict(created_at=time.time(), test_not_generated_yet=True, rules=rules,
                                           checkpoints={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*.pt')},
                                           metric='ten consecutive success ticks; cost=failure+time_price*remaining_duration_s'))
    summaries = []
    for split in ['test', 'delay']:
        rows = dataset(args.test, split, out)
        summaries.append(evaluate(rows, models, mean, scale, device, rules, out, split))
        write(out / 'results.json', dict(scope=__doc__, summaries=summaries, training_device=device,
                                       candidate_branches=3 * (args.train + args.validation + args.test * len(summaries))))
    print(json.dumps(dict(event='complete', output=str(out))), flush=True)


if __name__ == '__main__':
    main()
