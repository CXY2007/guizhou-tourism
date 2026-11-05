# GPT review · booking-cancel

- verdict: **needs_fix**
- findings: 5

| severity | file | line | problem | fix |
|---|---|---|---|---|
| high | app/blueprints/api.py | 458 | Payment and cancellation perform a separate read/check and write, so concurrent requests can both observe a pending booking and then overwrite each other's status. This can produce contradictory success responses and an incorrect final order state. | Use an atomic conditional update such as UPDATE ... WHERE id = ... AND user_id = ... AND status = 'pending', check the affected row count, and return the appropriate already-paid/already-cancelled or invalid-status error. Add concurrent transition tests. |
| medium | app/blueprints/api.py | 154 | Boolean JSON values are accepted as integer IDs and ratings because bool is a subclass of int and the checks do not explicitly reject bool. For example, true can target attraction ID 1 and be stored as a rating of 1; the same issue exists in comments_create. | Reject bool explicitly for attraction_id and rating before integer validation, and add tests for true/false values on both endpoints. |
| medium | app/blueprints/api.py | 60 | serialise_attraction returns raw name and city values even though the module otherwise uses attr_field and city_label for localized attraction data. Favorites and history therefore expose a different locale than orders and admin responses. | Serialize localized fields consistently, using attr_field(a, 'name') and city_label(a.city) (and the appropriate category localization helper), with regression tests for a non-default locale. |
| low | app/blueprints/api.py | 111 | The favorite status endpoint returns 200 with favorited=false for a nonexistent attraction, while the toggle endpoint returns not_found. This prevents clients from distinguishing an invalid/deleted attraction from a valid unfavorited one. | Load and validate the attraction first and return the same not_found error code and status used by favorites_toggle; add an endpoint test. |
| low | app/blueprints/api.py | 355 | The fallback forecast weekday labels are hardcoded Chinese characters, so weather responses are not localized when the provider omits week data. | Generate weekday labels through the i18n layer or return a locale-neutral weekday value for the client to localize, and add locale coverage. |
