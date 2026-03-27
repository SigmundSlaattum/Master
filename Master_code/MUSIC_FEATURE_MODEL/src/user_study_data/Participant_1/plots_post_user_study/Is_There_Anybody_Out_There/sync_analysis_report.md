# Synchronization Report — Is There Anybody Out There

**Participant:** Participant_1  
**Music reference:** pre-computed trajectory (dynamic tempo)  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 89 | 89 |
| Outlier threshold (ms) | 8.8 | 5.8 |
| Peaks retained | 85 | 88 |
| **Mean abs offset (ms)** | **2.09** | **1.92** |
| Median abs offset (ms) | 0.92 | 1.59 |
| Std abs offset (ms) | 2.54 | 1.85 |
| Min abs offset (ms) | 0.00 | 0.00 |
| Max abs offset (ms) | 8.37 | 5.74 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 50.6% | 43.2% |
| ≤ 2 ms | 60.0% | 53.4% |
| ≤ 5 ms | 82.4% | 95.5% |
| ≤ 10 ms | 100.0% | 100.0% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 0.17 ms |
| Percentage difference | 8.7% |
| Better condition | **Simple** |

> Simple achieved a mean absolute offset of 1.92 ms, outperforming Complex (2.09 ms) by 0.17 ms (8.7%).
