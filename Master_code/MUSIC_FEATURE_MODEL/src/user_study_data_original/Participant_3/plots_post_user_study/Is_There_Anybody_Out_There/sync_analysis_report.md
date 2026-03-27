# Synchronization Report — Is There Anybody Out There

**Participant:** Participant_3  
**Half-period correction:** offsets wrapped modulo half beat period  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 115 | 112 |
| Outlier threshold (ms) | 11.7 | 11.5 |
| Peaks retained | 108 | 108 |
| **Mean abs offset (ms)** | **2.33** | **2.24** |
| Median abs offset (ms) | 1.77 | 1.88 |
| Std abs offset (ms) | 2.03 | 2.15 |
| Min abs offset (ms) | 0.00 | 0.00 |
| Max abs offset (ms) | 11.05 | 10.76 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 27.8% | 33.3% |
| ≤ 2 ms | 55.6% | 50.9% |
| ≤ 5 ms | 90.7% | 90.7% |
| ≤ 10 ms | 99.1% | 98.1% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 0.09 ms |
| Percentage difference | 4.1% |
| Better condition | **Simple** |

> Simple achieved a mean absolute offset of 2.24 ms, outperforming Complex (2.33 ms) by 0.09 ms (4.1%).
