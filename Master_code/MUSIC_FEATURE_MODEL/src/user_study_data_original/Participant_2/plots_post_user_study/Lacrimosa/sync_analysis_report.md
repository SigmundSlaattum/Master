# Synchronization Report — Lacrimosa

**Participant:** Participant_2  
**Half-period correction:** offsets wrapped modulo half beat period  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 122 | 123 |
| Outlier threshold (ms) | 135.5 | 133.6 |
| Peaks retained | 122 | 123 |
| **Mean abs offset (ms)** | **70.93** | **57.95** |
| Median abs offset (ms) | 74.21 | 66.10 |
| Std abs offset (ms) | 32.27 | 37.81 |
| Min abs offset (ms) | 0.00 | 0.00 |
| Max abs offset (ms) | 119.42 | 119.88 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 4.1% | 12.2% |
| ≤ 2 ms | 4.1% | 12.2% |
| ≤ 5 ms | 4.1% | 12.2% |
| ≤ 10 ms | 5.7% | 16.3% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 12.98 ms |
| Percentage difference | 22.4% |
| Better condition | **Simple** |

> Simple achieved a mean absolute offset of 57.95 ms, outperforming Complex (70.93 ms) by 12.98 ms (22.4%).
