"""Portable NumPy inference for a frozen judge; excludes perception/control cost."""
import argparse
import json
import platform
import time
from pathlib import Path
import numpy as np


def predict(x, weights):
    z=(np.asarray(x,dtype=np.float32)-weights['mean'])/weights['scale']
    h=np.concatenate([np.repeat(z[:,None,:],3,axis=1),
                      np.broadcast_to(np.eye(3),(len(z),3,3))],axis=2).astype(np.float32)
    for layer in [0,2]:
        h=np.tanh(h@weights[f'w{layer}'].T+weights[f'b{layer}'])
    logits=h@weights['w4'].T+weights['b4']
    p=1/(1+np.exp(-np.clip(logits,-80,80)))
    return 1-p[...,0]+np.asarray(x,dtype=np.float32)[:,4,None]*6*p[...,1]


def export(root, output):
    import torch
    from physics_rsi import load_bundle, predict as torch_predict
    model=load_bundle(root/'counterexample_11.pt')
    weights=dict(mean=np.asarray(model['mean']),scale=np.asarray(model['scale']))
    for layer in [0,2,4]:
        weights[f'w{layer}']=model['state_dict'][f'{layer}.weight'].numpy()
        weights[f'b{layer}']=model['state_dict'][f'{layer}.bias'].numpy()
    np.savez(output,**weights)
    rows=json.loads((root/'test.json').read_text())+json.loads((root/'delay.json').read_text())
    x=np.asarray([r['x'] for r in rows],dtype=np.float32)
    actual,reference=predict(x,weights),torch_predict(model,x)
    precision=torch.get_float32_matmul_precision()
    tf32=torch.backends.cuda.matmul.allow_tf32
    torch.set_float32_matmul_precision('highest')
    torch.backends.cuda.matmul.allow_tf32=False
    full_precision=torch_predict(model,x)
    np.testing.assert_allclose(actual,full_precision,atol=2e-6,rtol=2e-6)
    stored=np.asarray(sum([json.loads((root/(s+'_decisions.json')).read_text())['counterexample_11'] for s in ['test','delay']],[]))
    changed=np.flatnonzero(actual.argmin(1)!=stored)
    return dict(contexts=len(x),max_abs_score_error_default_gpu=float(np.max(np.abs(actual-reference))),
                max_abs_score_error_fp32_gpu=float(np.max(np.abs(actual-full_precision))),
                same_stored_choices=int(len(x)-len(changed)),changed_context_indices=changed.tolist(),
                default_gpu_precision=precision,default_gpu_tf32=tf32,
                torch=torch.__version__,cuda=torch.version.cuda,
                checkpoint='counterexample_11.pt',selection='fixed method/seed, not selected on test performance')


def benchmark(model, rows, output):
    weights=dict(np.load(model,allow_pickle=False))
    x=np.asarray([r['x'] for r in json.loads(rows.read_text())],dtype=np.float32)
    for i in range(100):
        predict(x[i%len(x):i%len(x)+1],weights)
    samples=[]
    for i in range(2000):
        sample=x[i%len(x):i%len(x)+1]
        start=time.perf_counter_ns()
        predict(sample,weights).argmin(1)
        samples.append((time.perf_counter_ns()-start)/1e6)
    result=dict(unit='ms',context_batch=1,candidates=3,samples=len(samples),warmup=100,
                median=float(np.median(samples)),p95=float(np.quantile(samples,.95)),p99=float(np.quantile(samples,.99)),
                python=platform.python_version(),numpy=np.__version__,architecture=platform.machine(),
                scope='One resident NumPy decision head including normalization/scoring; no image sensing, IK, network, servo or safety logic')
    output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['export','benchmark'],required=True)
    p.add_argument('--run',type=Path)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--rows',type=Path)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    assert not args.output.exists()
    if args.mode=='export':
        assert not args.model.exists()
        report=export(args.run,args.model)
        args.output.write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
    else:
        benchmark(args.model,args.rows,args.output)
