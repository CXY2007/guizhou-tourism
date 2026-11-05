# GPT review · booking-cancel-v2

- verdict: **needs_fix**
- findings: 1

| severity | file | line | problem | fix |
|---|---|---|---|---|
| medium | app/blueprints/api.py | 291 | The public assistant endpoint assumes `message` and `session_id` are strings. JSON such as `{"message": 1}` or `{"message": "hello", "session_id": []}` raises `AttributeError` or `TypeError` and returns a 500 instead of the API's structured error response. | Validate both fields are strings before calling `.strip()` or slicing; return `invalid_params` for invalid types. Add tests covering non-string values for each field. |
