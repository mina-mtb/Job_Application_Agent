# Job Matching Criteria

> Load this file only when running the Job Matcher agent.

## Scoring Weights
| Dimension | Max Points | Notes |
|-----------|-----------|-------|
| Skill match | 35 | Required skills vs Mina's verified skills |
| Experience fit | 20 | Junior/mid = 20pts, Senior 8+ = 2pts |
| Location fit | 20 | Gothenburg=20, Remote Sweden=18, Other=5 |
| Language fit | 10 | English/Swedish OK, native-only = 3pts |
| AI/Cloud bonus | 10 | AI/ML/Cloud roles get bonus weight |
| Career value | 5 | Company quality & growth potential |

## Priority Thresholds
- **90–100** → Excellent — generate CV immediately
- **85–89** → High — generate CV
- **75–84** → Medium — review manually first
- **< 75** → Reject

## Hard Rejection Rules (before scoring)
1. Contains "8+ years" or "10+ years" in description
2. `compensation: unpaid`
3. Title matches: retail, sales associate, cashier, nurse, teacher
4. Language: "native Swedish only" with no English option
