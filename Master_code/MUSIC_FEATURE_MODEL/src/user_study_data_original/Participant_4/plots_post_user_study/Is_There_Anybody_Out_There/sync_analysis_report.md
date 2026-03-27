# Synchronization Report — Is There Anybody Out There

**Participant:** Participant_4  
**Half-period correction:** offsets wrapped modulo half beat period  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 115 | 113 |
| Outlier threshold (ms) | 12.7 | 5.6 |
| Peaks retained | 107 | 106 |
| **Mean abs offset (ms)** | **2.50** | **1.77** |
| Median abs offset (ms) | 1.98 | 1.42 |
| Std abs offset (ms) | 2.36 | 1.52 |
| Min abs offset (ms) | 0.00 | 0.00 |
| Max abs offset (ms) | 12.54 | 5.17 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 29.9% | 37.7% |
| ≤ 2 ms | 52.3% | 62.3% |
| ≤ 5 ms | 87.9% | 99.1% |
| ≤ 10 ms | 97.2% | 100.0% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 0.73 ms |
| Percentage difference | 41.1% |
| Better condition | **Simple** |

> Simple achieved a mean absolute offset of 1.77 ms, outperforming Complex (2.50 ms) by 0.73 ms (41.1%).
