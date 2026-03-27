# Synchronization Report — Is There Anybody Out There

**Participant:** Participant_5  
**Music reference:** pre-computed trajectory (dynamic tempo)  
**Outlier threshold:** mean + N×std (per condition)

## Per-Condition Statistics

| Metric | Complex | Simple |
|--------|-------:|-------:|
| Total peaks | 89 | 89 |
| Outlier threshold (ms) | 5.8 | 6.1 |
| Peaks retained | 86 | 88 |
| **Mean abs offset (ms)** | **1.55** | **2.11** |
| Median abs offset (ms) | 1.09 | 1.89 |
| Std abs offset (ms) | 1.69 | 1.88 |
| Min abs offset (ms) | 0.00 | 0.00 |
| Max abs offset (ms) | 5.45 | 5.90 |

## Accuracy Thresholds

| Within threshold | Complex | Simple |
|-----------------|-------:|-------:|
| ≤ 1 ms | 48.8% | 37.5% |
| ≤ 2 ms | 64.0% | 51.1% |
| ≤ 5 ms | 98.8% | 93.2% |
| ≤ 10 ms | 100.0% | 100.0% |

## Comparison

| Metric | Value |
|--------|------:|
| Difference in mean offset | 0.55 ms |
| Percentage difference | 35.6% |
| Better condition | **Complex** |

> Complex achieved a mean absolute offset of 1.55 ms, outperforming Simple (2.11 ms) by 0.55 ms (35.6%).
