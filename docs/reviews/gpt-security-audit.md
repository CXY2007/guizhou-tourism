# GPT review · security-audit

- verdict: **needs_fix**
- findings: 1

| severity | file | line | problem | fix |
|---|---|---|---|---|
| medium | app/blueprints/api.py | 325 | QWeather forecast `week` values are commonly numeric strings (`"1"` through `"7"`). These pass through unchanged, so the API returns numeric weekday labels instead of localized weekdays. | Recognize numeric weekday values and map them to the corresponding localized weekday, falling back to `fxDate` when the value is invalid. |
