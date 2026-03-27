# Synchronization Report — So Easy

**Participant:** Participant_5  
**Half-period correction:** offsets wrapped modulo half beat period  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 105 | 104 |
| Outlier threshold (ms) | 154.6 | 191.0 |
| Peaks retained | 105 | 104 |
| **Mean abs offset (ms)** | **80.53** | **89.04** |
| Median abs offset (ms) | 77.06 | 120.96 |
| Std abs offset (ms) | 37.03 | 50.98 |
| Min abs offset (ms) | 0.00 | 0.00 |
| Max abs offset (ms) | 134.90 | 125.25 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 1.9% | 21.2% |
| ≤ 2 ms | 1.9% | 21.2% |
| ≤ 5 ms | 1.9% | 21.2% |
| ≤ 10 ms | 1.9% | 21.2% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 8.51 ms |
| Percentage difference | 10.6% |
| Better condition | **Complex** |

> Complex achieved a mean absolute offset of 80.53 ms, outperforming Simple (89.04 ms) by 8.51 ms (10.6%).
