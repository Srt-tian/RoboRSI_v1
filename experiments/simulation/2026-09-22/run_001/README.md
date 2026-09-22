# Kinematic decision-timing experiment

This is a logic sandbox, not a physical robot result.

Configuration: `{"seeds": 24, "start_seed": 0, "decision_delay_s": 0.35, "simulation_dt_s": 0.005, "trace_dt_s": 0.05, "scenarios": ["nominal", "shift", "shift_during_wait", "occluded_shift", "slip", "tracking_fault"], "methods": ["fixed_plan", "instant_rules", "delayed_unchecked", "delayed_checked"]}`

## Aggregate results

| Method | Success / episodes | Mean simulated seconds | Stale adoptions | Stale discards |
| --- | ---: | ---: | ---: | ---: |
| fixed_plan | 24 / 144 | 1.875 | 0 | 0 |
| instant_rules | 120 / 144 | 2.317 | 0 | 0 |
| delayed_unchecked | 120 / 144 | 2.633 | 24 | 0 |
| delayed_checked | 120 / 144 | 2.517 | 0 | 24 |

All injected protection stops count in the denominator. Mean time includes successes and failures.
No inference calls, trained judgments, or learned RSI updates are evaluated. Instant rules are a strong baseline.

## Files

- `benchmark.json`: configuration, source hashes, every episode's events and metrics; 20 Hz visual traces for the first seed.
- `process.jsonl.gz`: every episode's complete 200 Hz simulated states, named columns, phase encoding and pending revision.
- `summary.csv` and `summary.svg`: editable result table.
- `videos/*.mp4`: six four-method comparisons at 20 fps, aligned by world time.
- `index.html`: local interactive player, timeline, event records, videos and downloads.
- `manifest.json`: file hashes, renderer and source provenance.

## Reproduce from the repository root

```bash
python -m roborsi.simulation --seeds 24 --start-seed 0 --decision-delay 0.35 --output runs/new_simulation
python scripts/export_simulation_media.py runs/new_simulation
python scripts/verify_paper_run.py runs/new_simulation
```

Simulation requires the project environment. Media export additionally needs Pillow and ffmpeg.

## Limitations

- Kinematic contact proxy; not Piper dynamics or a validated physical simulator.
- Analytic proposals with injected delay, no GPT/Jev/VLM inference or learned RSI.
- Privileged semantic revision detector and simplified visibility/grasp observations.
- Seed variation covers small position/noise changes; not independent real-world trials.
- 200 Hz is virtual simulation sampling; no measured host scheduling guarantee.
