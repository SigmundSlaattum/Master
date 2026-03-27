# Synchronization Report — Lacrimosa

**Participant:** Participant_5  
**Half-period correction:** offsets wrapped modulo half beat period  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 122 | 138 |
| Outlier threshold (ms) | 136.9 | 128.7 |
| Peaks retained | 122 | 138 |
| **Mean abs offset (ms)** | **75.82** | **46.45** |
| Median abs offset (ms) | 80.15 | 38.87 |
| Std abs offset (ms) | 30.55 | 41.14 |
| Min abs offset (ms) | 0.86 | 0.00 |
| Max abs offset (ms) | 119.84 | 119.87 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 0.8% | 22.5% |
| ≤ 2 ms | 0.8% | 23.9% |
| ≤ 5 ms | 0.8% | 24.6% |
| ≤ 10 ms | 1.6% | 29.7% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 29.38 ms |
| Percentage difference | 63.2% |
| Better condition | **Simple** |

> Simple achieved a mean absolute offset of 46.45 ms, outperforming Complex (75.82 ms) by 29.38 ms (63.2%).
