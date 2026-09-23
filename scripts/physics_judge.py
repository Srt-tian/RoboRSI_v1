"""Learn a typed sensor-macro judge on MuJoCo Fetch contact outcomes.

State-sensor corruption benchmark, NOT learned visual perception or official Jev.
Policy receives noisy/delayed object position, exact proprioception and known goal.
Candidate macros share the same fixed controller. Each scene evaluates all three
sensor choices from the same reset and noise sequence. No test labels in training.
"""
import argparse
import concurrent.futures
import gzip
import hashlib
import json
import os
from pathlib import Path
import time

os.environ.setdefault('MUJOCO_GL','egl')
import gymnasium as gym
import gymnasium_robotics
import numpy as np
import torch
from torch import nn
from physics_pilot import Controller

TASKS=['FetchPush-v4','FetchPickAndPlace-v4']
NAMES=['keep_sensor','fast_refresh','accurate_refresh']


def context(index, split):
    seed={'train':110000,'validation':220000,'test':330000,'delay':440000}[split]+index
    rng=np.random.default_rng(seed)
    return {'seed':seed,'task':TASKS[index%2],'noise_std':float(rng.uniform(.001,.045)),
            'fast_delay':int(rng.integers(2,9) if split!='delay' else rng.integers(9,16)),
            'accurate_delay':int(rng.integers(9,21) if split!='delay' else rng.integers(21,36)),
            'fast_std':float(rng.uniform(.003,.015)), 'accurate_std':.001,
            'time_price':float(rng.uniform(.015,.12)), 'split':split,'index':index}


def rollout(env,c,choice,*,record=False,writer=None):
    obs,_=env.reset(seed=c['seed']);controller=Controller(c['task'])
    rng=np.random.default_rng(c['seed']+901)
    bias=rng.normal(size=3);bias[2]=0
    initial=obs['observation'][3:6]+bias*c['noise_std']
    x=[float(c['task']==TASKS[1]),c['noise_std'],c['fast_delay']*.04,c['accurate_delay']*.04,c['fast_std'],c['time_price'],
       *(initial-obs['observation'][:3]),*(obs['desired_goal']-initial)]
    delay=[0,c['fast_delay'],c['accurate_delay']][choice]
    noise=[c['noise_std'],c['fast_std'],c['accurate_std']][choice]
    history=[];trace=[];streak=0;success=False
    for k in range(150):
        raw=obs['observation'];history.append(raw[3:6].copy())
        if k<delay:
            perceived=initial;action=np.r_[np.zeros(3),1.0]
        else:
            # Fixed bias and finite sample age simulate a tracking sensor.
            age=0 if choice==0 else delay
            perceived=history[max(0,k-age)]+bias*noise
            action=controller.action(raw[:3],perceived,obs['desired_goal'])
        obs,reward,terminated,truncated,info=env.step(action)
        streak=streak+1 if bool(info['is_success']) else 0
        if record:
            trace.append({'step':k+1,'t':(k+1)*.04,'qpos':env.unwrapped.data.qpos.tolist(),
                          'grip':obs['observation'][:3].tolist(),'object':obs['achieved_goal'].tolist(),
                          'perceived_object':perceived.tolist(),'goal':obs['desired_goal'].tolist(),
                          'stage':controller.stage,'action':action.tolist(),'contacts':int(env.unwrapped.data.ncon),
                          'success':bool(info['is_success']),'observation_age_s':0 if choice==0 else delay*.04})
        if writer:writer.append_data(env.render())
        if streak>=10:success=True;break
        if terminated or truncated:break
    duration=(k+1)*.04
    loss=float(not success)+c['time_price']*duration
    return {'x':list(map(float,x)),'success':success,'duration_s':duration,'cost':loss,'trace':trace}


def worker(items):
    gym.register_envs(gymnasium_robotics)
    envs={task:gym.make(task,max_episode_steps=150) for task in TASKS}
    results=[]
    for c in items:
        branches=[rollout(envs[c['task']],c,i) for i in range(3)]
        results.append({'context':c,'x':branches[0]['x'],'success':[b['success'] for b in branches],
                        'duration':[b['duration_s'] for b in branches],'cost':[b['cost'] for b in branches]})
    for e in envs.values():e.close()
    return results


def dataset(count,split,out):
    items=[context(i,split) for i in range(count)]
    chunks=[items[i:i+20] for i in range(0,count,20)]
    rows=[]
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        for result in pool.map(worker,chunks):
            rows.extend(result)
            print(json.dumps({'phase':'simulation','split':split,'contexts':len(rows),'total':count}),flush=True)
    (out/(split+'.json')).write_text(json.dumps(rows))
    return rows


def arrays(rows):
    return np.asarray([r['x'] for r in rows],dtype=np.float32),np.asarray([r['success'] for r in rows],dtype=np.float32),np.asarray([r['duration'] for r in rows],dtype=np.float32),np.asarray([r['cost'] for r in rows])


def model():return nn.Sequential(nn.Linear(12,64),nn.Tanh(),nn.Linear(64,64),nn.Tanh(),nn.Linear(64,6))


def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False))


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path)
    p.add_argument('--train',type=int,default=400);p.add_argument('--validation',type=int,default=120);p.add_argument('--test',type=int,default=200)
    args=p.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=False)
    write(out/'config.json',{'scope':__doc__,'counts':vars(args)|{'output':str(out)},'seeds':[11,22,33],
                            'feature_names':['pick_task','noise_std','fast_delay_s','accurate_delay_s','fast_std','time_price','object_minus_grip_x','object_minus_grip_y','object_minus_grip_z','goal_minus_object_x','goal_minus_object_y','goal_minus_object_z'],
                            'source_sha256':{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ['physics_judge.py','physics_pilot.py']}})
    train=dataset(args.train,'train',out);val=dataset(args.validation,'validation',out)
    xt,yt,dt,ct=arrays(train);xv,yv,dv,cv=arrays(val)
    mean=xt.mean(0);scale=np.maximum(xt.std(0),1e-5)
    device='cuda' if torch.cuda.is_available() else 'cpu'
    torch.set_num_threads(2)
    X=torch.tensor((xt-mean)/scale,device=device);Y=torch.tensor(yt,device=device);D=torch.tensor(dt/6,device=device)
    VX=torch.tensor((xv-mean)/scale,device=device)
    prices=xv[:,5,None];trials=[];nets=[]
    for seed in [11,22,33]:
        torch.manual_seed(seed);net=model().to(device);opt=torch.optim.Adam(net.parameters(),lr=.002)
        best=float('inf');curve=[]
        for epoch in range(1,301):
            net.train();v=net(X);loss=nn.functional.binary_cross_entropy_with_logits(v[:,:3],Y)+nn.functional.mse_loss(v[:,3:].sigmoid(),D)
            opt.zero_grad();loss.backward();opt.step()
            if epoch%5==0:
                net.eval()
                with torch.no_grad():pred=net(VX).sigmoid().cpu().numpy()
                choice=(1-pred[:,:3]+prices*pred[:,3:]*6).argmin(1)
                cost=float(cv[np.arange(len(val)),choice].mean())
                curve.append({'epoch':epoch,'train_loss':float(loss.detach()),'validation_cost':cost})
                if cost<best:
                    best=cost;best_epoch=epoch;torch.save({'state_dict':net.cpu().state_dict(),'mean':mean.tolist(),'scale':scale.tolist()},out/f'model_{seed}.pt');net.to(device)
        load=torch.load(out/f'model_{seed}.pt',weights_only=True);net.load_state_dict(load['state_dict']);net.eval();nets.append(net)
        trials.append({'seed':seed,'best_epoch':best_epoch,'validation_cost':best,'curve':curve})
        print(json.dumps({'phase':'trained','seed':seed,'best_validation_cost':best,'device':device}),flush=True)
    write(out/'trials.json',trials)
    fixed=int(cv.mean(0).argmin())
    thresholds=[]
    for t in np.linspace(.002,.045,30):
        choice=np.where(xv[:,1]>t,2,0);thresholds.append((float(cv[np.arange(len(val)),choice].mean()),float(t)))
    threshold=min(thresholds)[1]
    write(out/'frozen_protocol.json',{'created_at':time.time(),'test_not_generated_yet':True,'fixed_choice':fixed,'rule_threshold':threshold,'checkpoints':{str(seed):hashlib.sha256((out/f'model_{seed}.pt').read_bytes()).hexdigest() for seed in [11,22,33]},'metric':'10 consecutive standard-success ticks; cost = failure + time_price * elapsed_s','device':device})
    summaries=[]
    for split in ['test','delay']:
        rows=dataset(args.test,split,out);x,y,d,c=arrays(rows)
        choices={'always_keep':np.zeros(len(rows),int),'always_fast':np.ones(len(rows),int),'always_accurate':np.full(len(rows),2),'validation_fixed':np.full(len(rows),fixed),'uncertainty_rule':np.where(x[:,1]>threshold,2,0)}
        allpred={}
        for seed,net in zip([11,22,33],nets):
            with torch.no_grad():pred=net(torch.tensor((x-mean)/scale,device=device)).sigmoid().cpu().numpy()
            key=f'judge_seed{seed}';choices[key]=(1-pred[:,:3]+x[:,5,None]*pred[:,3:]*6).argmin(1);allpred[key]=pred.tolist()
        metrics={}
        for name,a in choices.items():
            metrics[name]={}
            for task in TASKS:
                ix=np.asarray([i for i,r in enumerate(rows) if r['context']['task']==task]);aa=a[ix]
                metrics[name][task]={'episodes':len(ix),'success_rate':float(y[ix,aa].mean()),'mean_cost':float(c[ix,aa].mean()),'duration_s':float(d[ix,aa].mean()),'choices':np.bincount(aa,minlength=3).tolist()}
        summaries.append({'split':split,'methods':metrics})
        write(out/(split+'_decisions.json'),{'choices':{k:v.tolist() for k,v in choices.items()},'predictions':allpred})
        gym.register_envs(gymnasium_robotics)
        import imageio.v2 as imageio
        for idx in [0,1]:
            row=rows[idx];env=gym.make(row['context']['task'],max_episode_steps=150,render_mode='rgb_array',width=640,height=480)
            for name in ['always_keep','always_accurate','judge_seed11']:
                a=int(choices[name][idx]);stem=f'{split}_{idx}_{name}'
                with imageio.get_writer(out/(stem+'.mp4'),fps=25) as writer: result=rollout(env,row['context'],a,record=True,writer=writer)
                with gzip.open(out/(stem+'.json.gz'),'wt') as f:json.dump({'context':row['context'],'method':name,'choice':a,**result},f)
            env.close()
        print(json.dumps({'phase':'evaluation','split':split,'metrics':metrics}),flush=True)
    write(out/'results.json',{'scope':__doc__,'summaries':summaries,'training_device':device,'candidate_branches':3*(args.train+args.validation+2*args.test),'test_contexts':2*args.test})


if __name__=='__main__':main()
