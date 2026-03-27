# Synchronization Report — Is There Anybody Out There

**Participant:** Participant_2  
**Music reference:** pre-computed trajectory (dynamic tempo)  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 86 | 89 |
| Outlier threshold (ms) | 6.7 | 6.4 |
| Peaks retained | 82 | 87 |
| **Mean abs offset (ms)** | **1.74** | **2.01** |
| Median abs offset (ms) | 1.15 | 1.54 |
| Std abs offset (ms) | 1.91 | 2.05 |
| Min abs offset (ms) | 0.00 | 0.00 |
| Max abs offset (ms) | 6.05 | 6.07 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 48.8% | 43.7% |
| ≤ 2 ms | 59.8% | 58.6% |
| ≤ 5 ms | 92.7% | 86.2% |
| ≤ 10 ms | 100.0% | 100.0% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 0.26 ms |
| Percentage difference | 15.2% |
| Better condition | **Complex** |

> Complex achieved a mean absolute offset of 1.74 ms, outperforming Simple (2.01 ms) by 0.26 ms (15.2%).
