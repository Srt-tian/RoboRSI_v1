# Typed judgment for RoboRSI · 2026-09-22

## Objective

Add a Jev-inspired, bounded decision interface to the offline RSI workflow while
preserving the coarse-plan compiler and fixed 200 Hz execution path.

## Design

- GPT proposes plans; the existing deterministic evaluator admits candidates;
  a typed judgment provider prioritizes review or requests more evidence.
- Choice questions select a route and candidate; Noul asks whether the supplied
  evidence supports candidate review. Code composes these independent answers.
- Explicit abstention, distribution validation, probability/margin thresholds,
  request fingerprints and age checks constrain acceptance. Scores are not
  calibrated robot success probabilities.
- Providers: disabled by default; recorded response replay; clearly synthetic
  demonstration; optional TypeSafe HTTP adapter with explicit network opt-in.
- No paid/model calls or model-weight downloads in this iteration. No new runtime
  feedback loop, autonomous motion, or generated-code execution.
- Track decisions through review/context artifacts. Add held-out probability
  evaluation so later model selection measures calibration and abstention.
- User steering: develop an independent research hypothesis instead of binding
  the architecture to Jev. Represent phase expectations and semantic context;
  recheck an advisory reply before admitting it for review.
- User steering: build a repeatable simulation and archive paper-ready local
  results, process states and videos. Keep proxy logic tests separate from
  physical validation and learned-model performance.

## Acceptance

- Reject unknown options, incomplete/nonfinite distributions, inconsistent
  choices, stale/mismatched replies, invalid candidate artifacts, and mixing
  candidates from different baseline/configuration comparisons.
- Geometry is required by default; explicitly numerical-only shadow ranking is
  marked as such. Model confidence cannot rescue rejected candidates.
- Offline demo, replay, HTTP contract tests, calibration tests, and existing
  historical regression pass without network or hardware.
- Dated primary-source survey distinguishes official API, independent trainable
  models, robotics applications, and papers. Update editable diagrams and docs.

## Implementation and verification

- v0.3: phase-contract routing, typed providers, abstention, distribution checks,
  request age/hash checks and pre/post inference context validation implemented.
- Optional judgment links survive explicit review and scoped planning context.
  Validation/test group isolation and selective-decision scoring implemented.
- Research survey covers 11 ecosystem projects and four direct Jev papers,
  with additional robotics/continuation comparisons. Proposal specifies a
  falsifiable scope, strong rule baseline, ablations and implementation gaps.
- Kinematic sandbox: 24 seeds × six scenarios × four methods = 576 episodes.
  All 269,616 states archived, six clock-aligned videos and editable result
  tables exported. No paid inference, weights, hardware or learned RSI updates.
- 56 offline tests pass; 34 historical archives and 12 new run files verify.
  Every new process episode has complete 5 ms timestamps and matching counts.
- Local browser verification passes: 576-episode load, seed 17 selection,
  5 ms single-step, method/scenario changes and H.264 MP4 decoding.
- Updated architecture and new judgment diagram structurally validate with
  zero warnings; PNGs visually inspected and editable SVGs exported.
- The paper workbench is served on the local control machine at
  `http://127.0.0.1:8790/paper/`; all artifacts also persist in the repository.

Publication follows these checks. Source fingerprints identify the simulation
implementation; the archived Git base alone is not its execution commit.
