# Synchronization Report — Is There Anybody Out There

**Participant:** Participant_2  
**Half-period correction:** offsets wrapped modulo half beat period  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 114 | 110 |
| Outlier threshold (ms) | 4.8 | 6.5 |
| Peaks retained | 112 | 104 |
| **Mean abs offset (ms)** | **1.81** | **1.98** |
| Median abs offset (ms) | 1.67 | 1.68 |
| Std abs offset (ms) | 1.09 | 1.78 |
| Min abs offset (ms) | 0.02 | 0.00 |
| Max abs offset (ms) | 4.73 | 6.19 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 25.0% | 33.7% |
| ≤ 2 ms | 59.8% | 58.7% |
| ≤ 5 ms | 100.0% | 92.3% |
| ≤ 10 ms | 100.0% | 100.0% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 0.17 ms |
| Percentage difference | 9.3% |
| Better condition | **Complex** |

> Complex achieved a mean absolute offset of 1.81 ms, outperforming Simple (1.98 ms) by 0.17 ms (9.3%).
