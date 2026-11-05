# GPT review · admin-users-v2

- verdict: **needs_fix**
- findings: 2

| severity | file | line | problem | fix |
|---|---|---|---|---|
| high | app/blueprints/admin.py | 64 | The last-admin check is not atomic on SQLite, the test database, or any backend where SELECT ... FOR UPDATE does not lock rows. Two concurrent requests can both observe two active admins and disable different admins, leaving no active administrator. Locking the rows being counted also does not reliably serialize the count against concurrent updates. | Serialize admin-disable operations with a database-level mechanism that works on the supported database (for example, a dedicated lock row or a transaction/advisory lock), then count active admins and update within that serialized transaction. Add a concurrency test against the production database backend. |
| medium | app/blueprints/admin.py | 174 | Attraction search interpolates the raw query into ILIKE patterns. User-supplied `%` and `_` act as wildcards, unlike the escaped search in the users endpoint, so filters can return unrelated attractions. | Escape backslash, percent, and underscore in the search term and pass escape="\\" to both ILIKE expressions; add tests for literal wildcard characters. |
