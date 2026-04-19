# SIRR

A 238-module symbolic calculation engine across classical esoteric
traditions — Abjad gematria, Jafr, Buduh magic squares, BaZi,
numerology, and more.

## Structure

- `Engine/` — core Python modules, runner, FastAPI server
- `Engine/fixtures/` — synthetic test profiles
- `Engine/tests/` — test suite (pytest)
- `Engine/web/` — landing page and demo views
- `Engine/web_backend/` — FastAPI endpoints (`/api/demo`, `/api/transliterate`, `/api/checkout`)
- `Docs/experience/` — synthetic showcase reference

## Running locally

```bash
cd Engine
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/              # full test suite
python runner.py fixtures/synthetic_profile.json --output /tmp/out.json
cd web_backend && uvicorn server:app --reload
```

## Demo

The demo endpoint renders a synthetic profile (FATIMA AHMED OMAR ALKATIB,
1990-03-15, Cairo) — all names and details are fictional.

## License

See LICENSE.
