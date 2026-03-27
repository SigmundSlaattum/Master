# Synchronization Report — So Easy

**Participant:** Participant_1  
**Half-period correction:** offsets wrapped modulo half beat period  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 105 | 105 |
| Outlier threshold (ms) | 160.6 | 184.2 |
| Peaks retained | 105 | 105 |
| **Mean abs offset (ms)** | **86.37** | **92.71** |
| Median abs offset (ms) | 79.38 | 120.89 |
| Std abs offset (ms) | 37.10 | 45.75 |
| Min abs offset (ms) | 0.00 | 0.00 |
| Max abs offset (ms) | 141.88 | 138.47 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 3.8% | 16.2% |
| ≤ 2 ms | 3.8% | 16.2% |
| ≤ 5 ms | 3.8% | 16.2% |
| ≤ 10 ms | 3.8% | 16.2% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 6.34 ms |
| Percentage difference | 7.3% |
| Better condition | **Complex** |

> Complex achieved a mean absolute offset of 86.37 ms, outperforming Simple (92.71 ms) by 6.34 ms (7.3%).
