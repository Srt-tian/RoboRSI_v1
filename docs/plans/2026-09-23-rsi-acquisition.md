# A bounded offline RSI acquisition experiment

Status: protocol frozen before collection. This is a hypothesis test of data selection,
not a claim that conventional active learning or nearest-neighbor regression is new.

## Question

Does collecting around cross-fitted decision errors improve a small typed judge more
than the same number of randomly acquired or model-disagreement-selected labels?
All methods use the same unchanged Fetch skills and sensor simulator as phase study 1.

## Fixed protocol

- Reuse only the old 600 training contexts and 180 validation contexts for acquisition
  design. Old test labels are not read by any training or selection command.
- CPU host builds 1,200 observable-only checkpoint contexts, half short/long delay,
  balanced across Push/Pick. No candidate rollouts or outcome labels during selection.
- Three-fold, task/stage-stratified cross fitting, three seeds, shared 6,402-parameter
  head. A held-out context's regret is the selected candidate's cost minus the best
  simulated candidate cost, averaged over three out-of-fold predictors.
- Counterexample score: inverse-distance weighted regret of 15 same-task neighbors
  in standardized observable features. This is not a learned world model.
- Disagreement score: entropy of three frozen judges' votes plus the average standard
  deviation of candidate cost estimates. Stronger active-learning control than random alone.
- Each acquisition method gets exactly 180 contexts (540 candidate rollouts), 45 per
  task/delay stratum. Targeted methods use 80% score ranking and 20% uniform exploration.
  Overlapping requests share recorded simulator results but count toward each budget.
- Updates begin from the same corresponding frozen seed model. Fixed normalizer,
  Adam 0.002, 400 updates, 256 contexts sampled per update. Replay-only uses old data
  with the same update budget; each acquisition arm adds its 180 selected contexts.
- Independent new validation: 180 contexts, balanced delay/ task mixture. Checkpoint
  selection every ten updates includes the unchanged initial checkpoint at step zero.
- Freeze all model hashes and rules before constructing fresh tests: 300 short-delay
  and 300 long-delay contexts. No test-directed revision of this protocol.
- Primary contrast: counterexample minus random mean cost across the balanced 600
  contexts after averaging the three fixed training seeds. 4,000 context bootstrap
  draws. Other contrasts/strata exploratory, no multiplicity adjustment.
- Only one acquisition draw is included. Uncertainty over acquisition seeds, camera
  inputs, additional tasks, multiple online decisions, and hardware remain outside scope.

Seed ranges: pilot 1,010,000; pool 1,110,000; validation 1,210,000; short test 1,310,000;
long test 1,410,000. Every range adds its context index and is disjoint from past studies.
All physical candidate traces are retained on the simulation host. Local Web receives
inputs, selections, cross-fit errors, training curves, metrics, and selected replays.

## Operational layout

CPU collection and model fitting may run on separate development hosts. Use dedicated
clean Git checkouts at the same published commit. Record each stage's package versions;
perform a small cross-host repeatability probe before scaling collection. No EIP job
submission or hardware access is part of this experiment. Do not mutate active checkouts.

Entry point: `scripts/physics_rsi.py --mode MODE --run RUN [--base PREVIOUS_PHASE_RUN]`.
Order: `pilot`, `pool`, `validation`, `select`, `acquired`, `update`, `test`, `delay`,
`evaluate`. Copy only the needed JSON/models between hosts; do not transfer full traces
to the control-plane workstation. Test collection requires the frozen protocol file.

## Acceptance and interpretation

Report selection failure and null/negative results. A mean improvement alone does not
establish better sample efficiency; compare the equal-budget random and disagreement
arms, not just the frozen model. A positive single-round result would motivate independent
acquisition seeds and harder tasks, not a claim of conference-ready innovation.
