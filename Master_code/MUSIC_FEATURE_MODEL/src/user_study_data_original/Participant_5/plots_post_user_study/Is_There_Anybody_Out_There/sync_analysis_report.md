# Synchronization Report — Is There Anybody Out There

**Participant:** Participant_5  
**Half-period correction:** offsets wrapped modulo half beat period  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 119 | 117 |
| Outlier threshold (ms) | 11.2 | 5.9 |
| Peaks retained | 110 | 115 |
| **Mean abs offset (ms)** | **2.41** | **2.06** |
| Median abs offset (ms) | 1.89 | 1.78 |
| Std abs offset (ms) | 2.16 | 1.82 |
| Min abs offset (ms) | 0.00 | 0.00 |
| Max abs offset (ms) | 10.66 | 5.89 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 25.5% | 38.3% |
| ≤ 2 ms | 55.5% | 53.0% |
| ≤ 5 ms | 89.1% | 93.9% |
| ≤ 10 ms | 99.1% | 100.0% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 0.36 ms |
| Percentage difference | 17.3% |
| Better condition | **Simple** |

> Simple achieved a mean absolute offset of 2.06 ms, outperforming Complex (2.41 ms) by 0.36 ms (17.3%).
