# Synchronization Report — Lacrimosa

**Participant:** Participant_4  
**Half-period correction:** offsets wrapped modulo half beat period  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 121 | 121 |
| Outlier threshold (ms) | 121.7 | 130.1 |
| Peaks retained | 121 | 121 |
| **Mean abs offset (ms)** | **49.66** | **56.54** |
| Median abs offset (ms) | 45.13 | 62.46 |
| Std abs offset (ms) | 36.03 | 36.78 |
| Min abs offset (ms) | 0.00 | 0.00 |
| Max abs offset (ms) | 119.75 | 118.58 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 10.7% | 12.4% |
| ≤ 2 ms | 10.7% | 12.4% |
| ≤ 5 ms | 12.4% | 14.0% |
| ≤ 10 ms | 16.5% | 15.7% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 6.88 ms |
| Percentage difference | 13.8% |
| Better condition | **Complex** |

> Complex achieved a mean absolute offset of 49.66 ms, outperforming Simple (56.54 ms) by 6.88 ms (13.8%).
