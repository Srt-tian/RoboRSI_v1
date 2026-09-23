# Standalone System One study

Analytical probabilistic grasp simulation. Learned NumPy models; no official Jev, language encoder, rigid-body physics or hardware validation.

- `config.json`: seeds, training configuration and source hashes.
- `trials.json`, `models/`: every training run and its validation-selected checkpoint.
- `frozen_protocol.json`: choices frozen before test contexts were constructed.
- `results.json`, `summary.csv`, `results.svg`: all held-out results and context-bootstrap intervals.
- `decisions.json.gz`: every test context, predictions, selected macro and first-draw state replay.
- `*.npz`: all saved branch outcome arrays; hidden rollout values never enter policy input.
- `*_sample0.mp4`: first context / first draw of each cohort, no success-based filtering.
- `source/`: exact sources used for this run, preserved across later refactors.

Run records are sealed and must not be overwritten. The browser viewer is a maintained shared tool, not a frozen dependency of the results.
