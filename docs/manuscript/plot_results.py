"""Rebuild publication figures and tables from audited numeric artifacts."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--audit', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = json.loads((args.run / 'results.json').read_text())
    audit = json.loads(args.audit.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                         'pdf.fonttype': 42, 'svg.fonttype': 'none'})
    fig, axes = plt.subplots(2, 2, figsize=(8.2, 5.5), sharex=True, constrained_layout=True)
    refs = ['async_refresh', 'task_phase_lookup', 'no_phase_mean', 'no_age_mean', 'no_history_mean']
    labels = ['Always async', 'Phase lookup', 'Without phase', 'Without age', 'Without history']
    for row, split in enumerate(['test', 'delay']):
        for col, task in enumerate(['FetchPush-v4', 'FetchPickAndPlace-v4']):
            ax = axes[row, col]
            ds = {v['comparison'].replace('full_mean minus ', ''): v for v in audit['paired_cost_differences']
                  if v['split'] == split and v['task'] == task}
            for i, ref in enumerate(refs):
                v = ds[ref]
                color = '#087f78' if v['ci95'][1] < 0 else '#b15844' if v['ci95'][0] > 0 else '#68798c'
                ax.errorbar(v['mean'], 4-i, xerr=[[v['mean']-v['ci95'][0]], [v['ci95'][1]-v['mean']]],
                            fmt='o', color=color, capsize=3, markersize=4)
            ax.axvline(0, color='#8c969f', ls='--', lw=.8)
            ax.set_yticks(range(5), labels[::-1])
            ax.set_title(('IID' if split == 'test' else 'Long delay')+' / '+('Push' if col == 0 else 'Pick'))
            ax.grid(axis='x', color='#e5e9ef', lw=.5)
            if row == 1:
                ax.set_xlabel('Cost(full) - cost(reference)')
    fig.savefig(args.output / 'paired_effects.pdf', bbox_inches='tight')
    fig.savefig(args.output / 'paired_effects.png', dpi=220, bbox_inches='tight')
    plt.close(fig)
    table = []
    methods = [('continue', '继续'), ('stop_refresh', '停住刷新'), ('async_refresh', '异步刷新'),
               ('task_phase_lookup', '阶段查表'), ('full', '完整判断器'), ('no_phase', '去阶段'),
               ('no_age', '去年龄'), ('no_history', '去历史')]
    for split in ['test', 'delay']:
        table.append('\\begin{table}[t]\n\\centering\\small\n')
        caption = '同分布留出测试' if split == 'test' else '长延迟留出测试'
        table.append('\\caption{'+caption+'。每个任务 180 个独立场景；网络方法为三个训练种子的均值。成功率越高越好，代价越低越好。}\\label{tab:'+split+'}\n')
        table.append('\\begin{tabular}{lrrrr}\\toprule\n方法 & Push 成功率 & Push 代价 & Pick 成功率 & Pick 代价\\\\\\midrule\n')
        summary = next(v for v in result['summaries'] if v['split'] == split)
        for key, name in methods:
            vals = []
            for task in ['FetchPush-v4', 'FetchPickAndPlace-v4']:
                if key in ['full', 'no_phase', 'no_age', 'no_history']:
                    v = next(v for v in audit['variant_means'] if v['split'] == split and v['task'] == task and v['method'] == key)
                else:
                    v = summary['methods'][key][task]
                vals.extend([f"{100*v['success_rate']:.1f}\\%", f"{v['mean_cost']:.4f}"])
            table.append(name+' & '+' & '.join(vals)+'\\\\\n')
        table.append('\\bottomrule\\end{tabular}\n\\end{table}\n')
    (args.output / 'results_tables.tex').write_text(''.join(table))


if __name__ == '__main__':
    main()
