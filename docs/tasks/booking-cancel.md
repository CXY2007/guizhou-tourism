# Task: booking cancel (small module)

## Boundaries
- Allowed to modify: `app/blueprints/api.py` (append only), `tests/test_booking_cancel.py` (new file).
- Forbidden: `app/templates/**`, `app/static/**`, `app/models.py`, `app/config.py`, other blueprints.
- Do not run `git commit`.

## Contract
Add `POST /api/bookings/<int:booking_id>/cancel`.

- Login required (use the existing `@login_required_api` decorator).
- Only the owner may cancel. Missing booking or another user's booking -> 404 `not_found`, message `订单不存在`.
- `pending` -> `cancelled`; return `{ok:true,data:{id,status:"cancelled"}}`.
- Already `cancelled` -> 409 `already_cancelled`, message `订单已取消`.
- `paid` -> 409 `cannot_cancel_paid`, message `已支付订单不可取消`.
- Any other status -> 409 `invalid_status`, message `订单当前不可取消`.
- No request body required.

## Tests
Create `tests/test_booking_cancel.py` using SQLite in-memory, mirroring the fixture style in `tests/test_d3d.py`:
- pending cancel succeeds -> 200, status `cancelled`
- cancel again -> 409 `already_cancelled`
- paid booking -> 409 `cannot_cancel_paid`
- another user's booking -> 404
- anonymous -> 401 `login_required`
- Use `with client.session_transaction() as session: session["_user_id"] = str(user_id); session["_fresh"] = True` for login.
- `WTF_CSRF_ENABLED = False` in the test config.

## Acceptance
- `python -m pytest tests -q` passes.
- Do not restart the server on port 8900 (it runs old code).
- Keep your final report short: changed files, pytest result, and the curl command DSH should run.
