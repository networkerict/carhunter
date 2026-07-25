# Scoring

## Score Components
- `car_score`
- `value_score`
- `options_score`
- `premium_score`
- `personal_score`
- `deal_score`
- `final_score`

## Recalculation
- Full pipeline includes scoring and deal score updates.
- Rescore mode recalculates score chain consistently via canonical orchestration.

## Data Quality Requirements
- Core score columns should never remain NULL after pipeline/rescore.
