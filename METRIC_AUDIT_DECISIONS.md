# Hockey Untapped — Metric Audit Decisions

This review separates the legacy manual cohort from V4 carry-in-linked data. Do not pool the two cohorts.

## Keep

| Metric | Definition / denominator | Why |
|---|---|---|
| Actual shot goal rate | Goals (`Shot_Result=Goal`) / shots | Direct outcome; never use `Led_To_Goal` as the goal count |
| Scoring-chance rate | Tagged chance shots / shots in the stated cohort | Useful descriptive shot-quality measure; report n and uncertainty |
| Carry-in count | Recorded Anaheim controlled carry-ins | Directly observed entry volume |
| First-shot timing from carry-in | First shot after a recorded carry-in, grouped by elapsed seconds | Matches the study question when `Entry_ID` and elapsed time are present |
| Traffic / Low-Value descriptors | Tagged shots / all shots in the descriptor cohort | Keep as overlapping shot descriptors, not additive shot categories |
| Second / Third+ chance tags | Tagged second/third+ shots / all shots in that tag cohort | Useful rebound/continuation descriptors if applied consistently |

## Revise

| Existing metric | Required change |
|---|---|
| Forced turnover → advantage | Do not create 267 synthetic possessions from 267 events. Use only actual tracker-linked `Possession_ID` sequences; report chance and goal outcomes separately. Keep legacy turnover event counts and direct event flags only. |
| Turnover advantage vs non-turnover | Do not compare unmatched legacy event flags. Build a V4 comparison cohort with consistent tracked-sequence rules and report group sizes and game coverage. |
| Activated D-Man outcome | Attribute outcomes only to the same tracked sequence. Report descriptive association, not causal impact. |
| Gap Close → turnover within 10s | Keep as a temporal association with one-to-one matching and period/game checks. Do not call it a caused turnover. Prefer a linked event sequence when available. |
| Possession chance rate | Rename to tracked-sequence chance rate until all possession starts/ends are modeled. Denominator is tracked sequences, not every true NHL possession. |
| Second-chance follow-up within 20s | Use tagged second-chance shots as numerator/denominator; do not use a 20-second follow-up window as a proxy for rebound chance quality. |
| Rush / Early / Sustained / Extended | In V4, use only rows with nonblank `Entry_ID` and nonnegative `Seconds_Since_Entry`. Legacy manually assigned labels remain a separate descriptive cohort. |

## Remove as currently interpreted

- Historical entry-timing claims: the legacy games do not have observed carry-ins, so their manual timing labels are not measured elapsed time from entry.
- Extended-shot comparison or projection based on n=2.
- “Led To Goal” as a goal counter or goal probability. It is an attribution tag, not a mutually exclusive shot outcome.
- Adding Traffic / Low-Value counts to timing-category totals; they overlap.
- Causal language for D-Man actions based only on time proximity.

## Add

1. **Entry conversion:** carry-ins with at least one shot / all recorded carry-ins.
2. **Entry chance conversion:** carry-ins with at least one tagged scoring-chance shot / all recorded carry-ins.
3. **Entry goal conversion:** carry-ins with at least one actual goal / all recorded carry-ins.
4. **Shots per entry:** all linked shots / recorded carry-ins, alongside the share of entries with no shot.
5. **Tracked-sequence outcomes:** share of tracked sequences with a shot, chance, or goal; label the incomplete sequence coverage clearly.
6. **Data-quality coverage:** share of shots with `Entry_ID`, share with `Possession_ID`, carry-ins per game, and games represented in each timing group.

## Reliability and projection rules

- Always show numerator, denominator, game count, and a 95% interval.
- For proportions, use Wilson intervals; for clustered observations, add a game-cluster bootstrap interval when at least two games contribute.
- n<20: highly unstable; use as a case series, not a ranking or projection.
- n=20–49: exploratory only.
- n=50–99 across multiple games: preliminary descriptive comparison; still not a dependable forecast.
- Initial predictive modeling should wait for roughly 100+ observations per category across at least 20 games, with stronger preference for 200+ observations and 30+ games. This is a practical minimum, not a guarantee.
- Goal prediction needs substantially more data than chance-tag prediction because goals are rarer. Use regularization, held-out games, calibration checks, and uncertainty intervals before presenting forecasts.
- Do not project a rate from two Extended observations or infer team-wide performance from a handful of games.

## Known V4 limitation

`Possession_ID` is currently a tracker-generated **tracked-sequence ID**, not a complete NHL possession reconstruction. Faceoffs, every loose-puck recovery, and every change of control are not fully modeled. It is suitable for linking the events the tracker observes, but not for claiming a census of all Anaheim possessions. The next data-model improvement should capture additional possession-start/end events before upgrading the label to true possession-level analytics.
