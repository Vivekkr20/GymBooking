# Pulse Gym Booking

A small, full-stack gym session booking system with a polished member experience and an operations-focused admin area.

## Run it

```powershell
cd outputs/gym-booking
python server.py
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080). The database and sample data are created automatically on first run.

## Test accounts

| Role | Email | Password |
| --- | --- | --- |
| Admin | `admin@pulsegym.test` | `MoveStrong2026!` |
| Member | `alex@pulsegym.test` | `MoveStrong2026!` |
| Member | `sam@pulsegym.test` | `MoveStrong2026!` |

## Design note

- Python's standard library HTTP server keeps the backend dependency-free and easy to inspect.
- SQLite is the real relational database; foreign keys and indexes represent the domain relationships.
- Opaque, expiring bearer tokens are stored as hashes; passwords use PBKDF2-SHA256 with per-user salts.
- Booking and cancellation use `BEGIN IMMEDIATE` transactions so a session cannot oversell under contention.
- A partial unique index enforces one active booking per member and session.
- A cancellation promotes the oldest waiting member in the same transaction when the session has not started.
- The frontend is a framework-free SPA with hash routing, protected views, optimistic booking and polling.
- Times are stored as ISO local timestamps for this focused take-home exercise; production would use UTC plus a venue timezone.

## Assumptions

- Sessions belong to one gym and have a fixed one-hour duration.
- All members may view future sessions; only members can create bookings or join waitlists.
- Test accounts and fixture sessions are regenerated only when the database does not yet exist.
- A full session can have a waitlist; members join it from the same session card.

## API overview

`POST /api/auth/register`, `POST /api/auth/login`, `GET /api/sessions`, `POST /api/sessions`, `POST /api/sessions/:id/book`, `POST|DELETE /api/sessions/:id/waitlist`, `GET /api/bookings/me`, `DELETE /api/bookings/:id`, `GET /api/admin/sessions/:id/bookings`, and `POST /api/admin/check-in`.

Every API error has the shape `{ "error": { "code", "message", "fields?" } }`.

## Deploy on GitHub + Vercel + Neon

1. **GitHub:** create an empty repo, then from this folder run
   `git init`, `git add .`, `git commit -m "Initial commit"`, `git branch -M main`,
   `git remote add origin <your-repo-url>`, `git push -u origin main`.
   (`.gitignore` keeps `.env`, `gym_booking.db` and `__pycache__` out of the repo.)
2. **Vercel:** Add New -> Project -> import the repo. Framework preset: **Other**. Leave build/output settings empty.
3. **Database:** in Vercel go to Storage / Marketplace, add **Neon Postgres** and connect it to the project (this sets `DATABASE_URL`).
4. **Environment variables** (Project Settings -> Environment Variables):
   - `DATABASE_URL` - Neon connection string (set automatically by the integration)
   - `GYM_SECRET` - a long random string (e.g. `python -c "import secrets; print(secrets.token_urlsafe(48))"`)
   - `GYM_TIMEZONE` - gym timezone, default `Asia/Kolkata`
5. **Deploy** (or Redeploy after adding variables). Check `https://<your-app>.vercel.app/api/health` returns `{"ok": true}`.

The first production request creates the tables and demo data. Change or remove the demo accounts before a real launch.
