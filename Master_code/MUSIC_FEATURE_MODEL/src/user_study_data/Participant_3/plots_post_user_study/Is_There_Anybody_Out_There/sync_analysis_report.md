# Synchronization Report — Is There Anybody Out There

**Participant:** Participant_3  
**Music reference:** pre-computed trajectory (dynamic tempo)  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 88 | 88 |
| Outlier threshold (ms) | 6.0 | 5.9 |
| Peaks retained | 85 | 85 |
| **Mean abs offset (ms)** | **1.69** | **2.06** |
| Median abs offset (ms) | 0.25 | 1.97 |
| Std abs offset (ms) | 1.92 | 1.66 |
| Min abs offset (ms) | 0.00 | 0.00 |
| Max abs offset (ms) | 5.86 | 5.59 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 52.9% | 30.6% |
| ≤ 2 ms | 57.6% | 50.6% |
| ≤ 5 ms | 94.1% | 95.3% |
| ≤ 10 ms | 100.0% | 100.0% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 0.37 ms |
| Percentage difference | 21.7% |
| Better condition | **Complex** |

> Complex achieved a mean absolute offset of 1.69 ms, outperforming Simple (2.06 ms) by 0.37 ms (21.7%).
