# Synchronization Report — Is There Anybody Out There

**Participant:** Participant_6  
**Music reference:** pre-computed trajectory (dynamic tempo)  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 88 | 89 |
| Outlier threshold (ms) | 20.8 | 6.3 |
| Peaks retained | 83 | 85 |
| **Mean abs offset (ms)** | **4.15** | **1.89** |
| Median abs offset (ms) | 2.84 | 1.52 |
| Std abs offset (ms) | 5.16 | 1.81 |
| Min abs offset (ms) | 0.00 | 0.00 |
| Max abs offset (ms) | 19.99 | 6.15 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 41.0% | 41.2% |
| ≤ 2 ms | 45.8% | 60.0% |
| ≤ 5 ms | 67.5% | 91.8% |
| ≤ 10 ms | 88.0% | 100.0% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 2.25 ms |
| Percentage difference | 119.1% |
| Better condition | **Simple** |

> Simple achieved a mean absolute offset of 1.89 ms, outperforming Complex (4.15 ms) by 2.25 ms (119.1%).
