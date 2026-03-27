# Synchronization Report — Is There Anybody Out There

**Participant:** Participant_6  
**Half-period correction:** offsets wrapped modulo half beat period  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 116 | 115 |
| Outlier threshold (ms) | 65.3 | 34.4 |
| Peaks retained | 106 | 106 |
| **Mean abs offset (ms)** | **12.21** | **7.85** |
| Median abs offset (ms) | 3.88 | 3.93 |
| Std abs offset (ms) | 17.22 | 9.32 |
| Min abs offset (ms) | 0.00 | 0.00 |
| Max abs offset (ms) | 64.46 | 32.11 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 17.9% | 27.4% |
| ≤ 2 ms | 28.3% | 32.1% |
| ≤ 5 ms | 54.7% | 59.4% |
| ≤ 10 ms | 68.9% | 72.6% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 4.36 ms |
| Percentage difference | 55.5% |
| Better condition | **Simple** |

> Simple achieved a mean absolute offset of 7.85 ms, outperforming Complex (12.21 ms) by 4.36 ms (55.5%).
