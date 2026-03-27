# Synchronization Report — So Easy

**Participant:** Participant_1  
**Music reference:** pre-computed trajectory (dynamic tempo)  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 61 | 95 |
| Outlier threshold (ms) | 134.7 | 184.0 |
| Peaks retained | 61 | 95 |
| **Mean abs offset (ms)** | **73.18** | **71.21** |
| Median abs offset (ms) | 76.74 | 119.33 |
| Std abs offset (ms) | 30.74 | 56.39 |
| Min abs offset (ms) | 0.00 | 0.00 |
| Max abs offset (ms) | 124.03 | 133.92 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 3.3% | 32.6% |
| ≤ 2 ms | 3.3% | 32.6% |
| ≤ 5 ms | 3.3% | 32.6% |
| ≤ 10 ms | 3.3% | 32.6% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 1.97 ms |
| Percentage difference | 2.8% |
| Better condition | **Simple** |

> Simple achieved a mean absolute offset of 71.21 ms, outperforming Complex (73.18 ms) by 1.97 ms (2.8%).
