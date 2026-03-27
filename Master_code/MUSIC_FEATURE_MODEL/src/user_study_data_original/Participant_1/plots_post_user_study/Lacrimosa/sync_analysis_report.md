# Synchronization Report — Lacrimosa

**Participant:** Participant_1  
**Half-period correction:** offsets wrapped modulo half beat period  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 141 | 129 |
| Outlier threshold (ms) | 138.9 | 133.1 |
| Peaks retained | 141 | 129 |
| **Mean abs offset (ms)** | **65.22** | **62.65** |
| Median abs offset (ms) | 72.89 | 72.25 |
| Std abs offset (ms) | 36.85 | 35.25 |
| Min abs offset (ms) | 0.00 | 0.00 |
| Max abs offset (ms) | 119.62 | 119.79 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 9.2% | 8.5% |
| ≤ 2 ms | 9.2% | 8.5% |
| ≤ 5 ms | 9.2% | 8.5% |
| ≤ 10 ms | 12.1% | 10.9% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 2.57 ms |
| Percentage difference | 4.1% |
| Better condition | **Simple** |

> Simple achieved a mean absolute offset of 62.65 ms, outperforming Complex (65.22 ms) by 2.57 ms (4.1%).
