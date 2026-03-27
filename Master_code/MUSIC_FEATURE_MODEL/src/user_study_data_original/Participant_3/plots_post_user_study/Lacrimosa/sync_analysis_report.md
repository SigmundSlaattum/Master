# Synchronization Report — Lacrimosa

**Participant:** Participant_3  
**Half-period correction:** offsets wrapped modulo half beat period  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 122 | 121 |
| Outlier threshold (ms) | 129.7 | 121.8 |
| Peaks retained | 122 | 121 |
| **Mean abs offset (ms)** | **53.58** | **50.04** |
| Median abs offset (ms) | 50.59 | 51.30 |
| Std abs offset (ms) | 38.05 | 35.89 |
| Min abs offset (ms) | 0.00 | 0.00 |
| Max abs offset (ms) | 118.69 | 119.33 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 9.0% | 14.9% |
| ≤ 2 ms | 9.0% | 14.9% |
| ≤ 5 ms | 9.8% | 14.9% |
| ≤ 10 ms | 14.8% | 19.0% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 3.55 ms |
| Percentage difference | 7.1% |
| Better condition | **Simple** |

> Simple achieved a mean absolute offset of 50.04 ms, outperforming Complex (53.58 ms) by 3.55 ms (7.1%).
