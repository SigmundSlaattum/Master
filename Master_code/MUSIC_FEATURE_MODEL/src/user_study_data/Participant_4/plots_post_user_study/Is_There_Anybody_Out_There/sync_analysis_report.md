# Synchronization Report — Is There Anybody Out There

**Participant:** Participant_4  
**Music reference:** pre-computed trajectory (dynamic tempo)  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 88 | 90 |
| Outlier threshold (ms) | 6.0 | 6.1 |
| Peaks retained | 84 | 88 |
| **Mean abs offset (ms)** | **1.63** | **2.01** |
| Median abs offset (ms) | 0.69 | 1.63 |
| Std abs offset (ms) | 1.89 | 1.92 |
| Min abs offset (ms) | 0.00 | 0.00 |
| Max abs offset (ms) | 5.93 | 6.04 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 53.6% | 40.9% |
| ≤ 2 ms | 60.7% | 56.8% |
| ≤ 5 ms | 94.0% | 89.8% |
| ≤ 10 ms | 100.0% | 100.0% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 0.38 ms |
| Percentage difference | 23.0% |
| Better condition | **Complex** |

> Complex achieved a mean absolute offset of 1.63 ms, outperforming Simple (2.01 ms) by 0.38 ms (23.0%).
