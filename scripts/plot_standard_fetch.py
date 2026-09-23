"""Standalone benchmark-readiness plots; none are new JEV efficacy results."""
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'experiments/mujoco/2026-09-23'
evaluation = json.loads((DATA / 'standard_fetch_001/evaluation/summary.json').read_text())['summaries']
curve = json.loads((DATA / 'slide_her_001/curve.json').read_text())
plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False,
                     'figure.facecolor': 'white', 'axes.facecolor': 'white'})
fig, axes = plt.subplots(1, 3, figsize=(16, 4.5), constrained_layout=True)
ps = np.array([r['success'] for r in evaluation])
ns = np.array([r['episodes'] for r in evaluation])
z = 1.96
denom = 1 + z*z/ns
center = (ps + z*z/(2*ns))/denom
radius = z*np.sqrt(ps*(1-ps)/ns+z*z/(4*ns*ns))/denom
axes[0].bar(['Reach', 'Push', 'Pick', 'Slide'], 100*ps, color=['#087f78']*3+['#bf654d'])
axes[0].errorbar(range(4), 100*ps, yerr=np.maximum(0,100*np.array([ps-center+radius,center+radius-ps])),
                 fmt='none', ecolor='#172b45', capsize=4)
axes[0].set(ylabel='Final-step success (%)', ylim=(0,110), title='Frozen skills: 100 held-out seeds/task')
for i, value in enumerate(ps): axes[0].text(i, 100*value+5, f'{100*value:.0f}%', ha='center')
x = np.array([r['steps'] for r in curve])/1000
axes[1].plot(x, [100*r['validation_success'] for r in curve], 'o-', color='#bf654d')
axes[1].set(xlabel='Training transitions (thousands)', ylabel='Final-step success (%)', ylim=(-3,100),
             title='Slide SAC + HER: validation only')
axes[2].plot(x, [1000*r['mean_final_distance'] for r in curve], 'o-', color='#436eb3')
axes[2].axhline(50, color='#087f78', linestyle='--', label='Task threshold')
axes[2].set(xlabel='Training transitions (thousands)', ylabel='Mean final distance (mm)', ylim=(0,600),
             title='Same 50 validation seeds at every checkpoint')
axes[2].legend(frameon=False)
for ax in axes: ax.grid(axis='y', alpha=.18); ax.set_axisbelow(True)
fig.suptitle('Standard Fetch-v4: default 50-step full episodes | Baseline qualification, not JEV efficacy', fontsize=13)
output = ROOT / 'docs/assets/standard_fetch_readiness'
output.parent.mkdir(exist_ok=True)
fig.savefig(output.with_suffix('.png'), dpi=180)
fig.savefig(output.with_suffix('.pdf'))
plt.close(fig)
print(json.dumps({'png': str(output.with_suffix('.png')), 'pdf': str(output.with_suffix('.pdf'))}))
