# Synchronization Report — So Easy

**Participant:** Participant_2  
**Half-period correction:** offsets wrapped modulo half beat period  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 105 | 104 |
| Outlier threshold (ms) | 159.8 | 184.0 |
| Peaks retained | 105 | 104 |
| **Mean abs offset (ms)** | **87.20** | **102.97** |
| Median abs offset (ms) | 79.94 | 121.36 |
| Std abs offset (ms) | 36.28 | 40.52 |
| Min abs offset (ms) | 0.00 | 0.00 |
| Max abs offset (ms) | 141.45 | 135.11 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 1.0% | 12.5% |
| ≤ 2 ms | 1.0% | 12.5% |
| ≤ 5 ms | 1.0% | 12.5% |
| ≤ 10 ms | 1.0% | 12.5% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 15.77 ms |
| Percentage difference | 18.1% |
| Better condition | **Complex** |

> Complex achieved a mean absolute offset of 87.20 ms, outperforming Simple (102.97 ms) by 15.77 ms (18.1%).
