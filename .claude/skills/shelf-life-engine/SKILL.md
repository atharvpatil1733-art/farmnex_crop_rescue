---
name: shelf-life-engine
description: Rules for the FarmNex Crop Rescue shelf-life and matching logic in crop_rescue/core/ (Q10 model, freshness accumulation, FRESH/AT_RISK/SPOILED, 48-hour alert, buyer scoring). Load before creating or editing anything in crop_rescue/core/, crops.json, or the tests for them.
---

# Shelf-life engine rules

This is the part the SIH judges will ask about. It must stay **small, pure and explainable in one breath**:
> "Each crop has a sourced shelf life at its ideal temperature. Every 10 °C hotter halves it. We add up how much freshness each hour eats, and alert the farmer with at least 48 hours to go."

## Non-negotiables

1. **Pure functions only** in `crop_rescue/core/`. No DB, no FastAPI, no `datetime.now()`, no env reads. Config values and `now` come in as arguments.
2. **Data comes only from `crop_rescue/data/crops.json`.** Never change a number in it. Never add a 9th crop. If a value seems wrong, stop and tell the user.
3. **Q10 is an assumption** (default 2.0). Every place that shows life-at-temperature must also be able to say "Q10 = 2 (assumption)".
4. **Never extend life beyond the handbook value.** If `T <= ref_temp_c`, return `ref_life_hours`.

## Formulas (implement exactly)

```python
def life_hours(ref_life_hours, ref_temp_c, temp_c, q10):
    if temp_c <= ref_temp_c:
        return ref_life_hours
    return ref_life_hours / q10 ** ((temp_c - ref_temp_c) / 10)

# per check
freshness_used = min(1.0, freshness_used + elapsed_hours / life_hours(..., temp_during_interval, ...))
remaining_hours = max(0.0, (1 - freshness_used) * life_hours(..., temp_now, ...))
```

Status:
```
remaining <= 0                              -> SPOILED
remaining <= alert_hours + interval_hours   -> AT_RISK   (48 + 12 = 60 by default)
else                                        -> FRESH
```
`SOLD` is set only by the API, never by the engine. The engine skips SOLD and SPOILED lots.

## Sanity numbers (use them as test fixtures; Q10 = 2)

| crop | at 25 °C | at 30 °C |
|---|---|---|
| tomato (168 h @ 17 °C) | ≈ 96.5 h | ≈ 68.2 h |
| spinach (240 h @ 0 °C) | ≈ 42.4 h | 30.0 h |
| cauliflower (504 h @ 0 °C) | ≈ 89.1 h | 63.0 h |

If your implementation doesn't reproduce these to 0.1 h, it's wrong.

## Matching (core/matching.py)

The pipeline is filter, then score, then take the top N. Follow the steps in docs/SPEC.md "Algorithm" §5. Keep in mind:
- Haversine × road factor. Don't call any maps API.
- Min–max normalise each score component across the candidates. If all candidates are equal, that component is 1.0 (avoid divide-by-zero).
- The `reason` string is generated from the numbers, one line, e.g. `₹18.4/kg after transport · 12 km · 30 h to spare`.
- 0 candidates is a valid result. Return `[]` and let the API explain why.

## Style

- Type hints everywhere, `@dataclass(frozen=True)` for `Crop`, `LotState`, `BuyerOffer`, `Match`.
- Each function gets a docstring with a short example. Judges may read this code.
- No clever one-liners. Readability beats brevity here.
