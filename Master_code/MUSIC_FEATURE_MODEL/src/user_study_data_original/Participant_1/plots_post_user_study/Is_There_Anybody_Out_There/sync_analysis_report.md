# Synchronization Report — Is There Anybody Out There

**Participant:** Participant_1  
**Half-period correction:** offsets wrapped modulo half beat period  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 116 | 113 |
| Outlier threshold (ms) | 7.3 | 5.9 |
| Peaks retained | 112 | 110 |
| **Mean abs offset (ms)** | **2.25** | **1.80** |
| Median abs offset (ms) | 1.87 | 1.44 |
| Std abs offset (ms) | 1.57 | 1.75 |
| Min abs offset (ms) | 0.03 | 0.00 |
| Max abs offset (ms) | 7.08 | 5.81 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 25.0% | 44.5% |
| ≤ 2 ms | 51.8% | 59.1% |
| ≤ 5 ms | 94.6% | 91.8% |
| ≤ 10 ms | 100.0% | 100.0% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 0.45 ms |
| Percentage difference | 25.1% |
| Better condition | **Simple** |

> Simple achieved a mean absolute offset of 1.80 ms, outperforming Complex (2.25 ms) by 0.45 ms (25.1%).
