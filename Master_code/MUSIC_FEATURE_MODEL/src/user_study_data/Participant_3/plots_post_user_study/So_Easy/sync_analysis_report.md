# Synchronization Report — So Easy

**Participant:** Participant_3  
**Music reference:** pre-computed trajectory (dynamic tempo)  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 63 | 95 |
| Outlier threshold (ms) | 127.2 | 180.3 |
| Peaks retained | 62 | 95 |
| **Mean abs offset (ms)** | **70.21** | **66.88** |
| Median abs offset (ms) | 76.25 | 82.87 |
| Std abs offset (ms) | 27.25 | 56.73 |
| Min abs offset (ms) | 5.34 | 0.00 |
| Max abs offset (ms) | 122.41 | 134.34 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 0.0% | 36.8% |
| ≤ 2 ms | 0.0% | 36.8% |
| ≤ 5 ms | 0.0% | 36.8% |
| ≤ 10 ms | 3.2% | 36.8% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 3.33 ms |
| Percentage difference | 5.0% |
| Better condition | **Simple** |

> Simple achieved a mean absolute offset of 66.88 ms, outperforming Complex (70.21 ms) by 3.33 ms (5.0%).
