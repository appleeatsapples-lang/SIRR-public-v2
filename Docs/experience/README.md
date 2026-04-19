# Experience — SIRR Showcase

This directory hosts the JSX visual showcase that renders the engine's
synthetic demo profile (FATIMA AHMED OMAR ALKATIB, 1990-03-15, Cairo).

The showcase is a deferred Codex deliverable. The JSON shape any future
JSX consumer should bind to is `Engine/fixtures/synthetic_output.json`
(238 modules + synthesis + psychological_mirror).

For the live machine-rendered demo, run the local server:

```
cd Engine
pip install -r requirements.txt
cd web_backend && uvicorn server:app --reload
# visit http://localhost:8000/view/demo
```
