# Hockey Untapped

Hockey Untapped is a Python-based hockey tracking and analytics project. It combines manually tagged game events with NHL data and analysis scripts to evaluate team and player performance.

## Project areas

- **Live event tracking:** `OCR Tracker/ocr_tracker.py` records manually tagged events and exports them to CSV.
- **Scoreboard capture tools:** `OCR Tracker/calibrate_broadcast.py` saves screen coordinates for a broadcast's game clock and period; `OCR Tracker/diagnose_ocr.py` tests the configured clock regions.
- **NHL data exploration:** `nhl_probe.py` queries NHL web endpoints for a team's schedule and a selected game's play-by-play data.
- **Data processing and analysis:** `preprocess_events.py`, `master_data_script.py`, `analytics.py`, and `dman_impact.py` support data preparation, aggregation, and analysis.
- **Data:** `raw_data/`, `enriched_data/`, `analytics_reports/`, and `master_dataset.csv` contain tracking and analysis outputs. Older material is kept under `archive/`.

## Current live tracker

The current tracker uses keyboard hotkeys to record events while a separate loop reads the game clock and period from a selected on-screen scoreboard using OCR.

### Event controls

| Key | Event |
|---|---|
| 1 | DZ Blueline Play Shut Down |
| 2 | D-Man Aggressive Gap Close |
| 3 | DZ → OZ Transition Completed |
| 4 | Stretch Pass → OZ Possession |
| 5 | Rush Shot (<5s after zone entry) |
| 6 | Early Possession Shot (<10s) |
| 7 | Sustained Possession Shot (10–30s) |
| x | Extended Possession Shot (>30s) |
| 8 | 2nd Scoring Chance (same possession) |
| 9 | 3rd+ Scoring Chance (same possession) |
| 0 | Shot With Traffic |
| - | Low-Value Shot |
| = | OZ Turnover Forced |
| a | Activated D-Man (OZ) |
| l | Lost Possession |

Modifiers apply to the most recently logged event: `s` = scoring chance, `p` = penalty drawn, `g` = led to goal. `Backspace` undoes the last event; `Esc` stops tracking and exports the session CSV.

The CSV includes team, game clock, period, event, scoring-chance flag, penalty flag, goal flag, and shot-result field.

## Setup

Use Python 3 on Windows. Install the Python packages used by the OCR tracker:

```powershell
python -m pip install Pillow pytesseract keyboard
```

Install the Tesseract OCR application separately and ensure its executable path matches the setting near the top of `OCR Tracker/ocr_tracker.py` (currently `C:\\Program Files\\Tesseract-OCR\\tesseract.exe`).

Run the tracker from the project directory:

```powershell
python "OCR Tracker/ocr_tracker.py"
```

The tracker asks for a configured scoreboard profile, team, opponent, and game date. Keep the scoreboard visible on the captured desktop while tracking.

## Recent development notes (November 23–25, 2026)

- Set up and tested the Python OCR dependencies, including Pillow and pytesseract; the Tesseract executable is configured separately from the Python package.
- Added the OCR tracker workflow and supporting calibration, diagnostic, and test scripts.
- Updated the tracker and supporting scripts to resolve project paths from each script's location, using a shared `OCR Tracker/broadcast_configs.json` and a project-level `raw_data/` output directory. This avoids depending on the current PowerShell working directory.
- Created and adjusted broadcast-specific clock and period capture regions. Screen capture troubleshooting included moving the game feed to the primary monitor and checking the captured desktop coordinates.
- Diagnosed inconsistent clock recognition. A manual preprocessing test (grayscale, 4× resize, increased contrast, and sharpening) successfully read `18:02` across multiple Tesseract page-segmentation modes. This was a successful test, not yet an integrated change to the tracker.
- Confirmed that OCR can be sensitive to scoreboard layout, region placement, and image quality. The tracker currently retains its last successfully read clock if a later OCR read fails, so stale timestamps still need handling before dependable long sessions.
- Began NHL API exploration in `nhl_probe.py`. The current probe retrieves a team schedule, selects a completed game, and inspects its play-by-play events and situation codes. It does not yet provide the live clock to the tracker.

## Next development step: NHL API clock source

Before changing the live tracker, validate the NHL web API against an active game. The likely starting points are:

- `https://api-web.nhle.com/v1/score/now` to find current games and their game IDs.
- `https://api-web.nhle.com/v1/gamecenter/{game_id}/landing` to inspect one game's live state, period, and clock.
- `https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play` for event-level play-by-play data.

These are publicly accessible NHL website endpoints, not a guaranteed stable, officially supported developer API. Verify the live response fields, update cadence, pause/intermission behavior, and reliability before depending on them.

The planned design is to keep the existing hotkeys, event definitions, event modifiers, and CSV export. Replace only the clock/period provider with a small data-source layer: NHL API as the preferred source, with OCR retained as an optional fallback if needed. Do not remove the OCR tools until the API path has passed live-game testing.

## Important metric notes

- Possession starts: `1` (DZ blue-line shutdown) and `=` (forced OZ turnover).
- Puck movement while already in possession: `3` (DZ → OZ transition) and `4` (stretch pass → OZ possession).
- D-man actions: `2` (aggressive gap close) and `a` (activated D-man in OZ).
- Timed-shot keys `5`, `6`, `7`, and `x` are measured from zone entry, not possession start.
- Modifiers `s`, `p`, and `g` apply to the last logged event.

See [Metrics definitions](Metrics%20definitions.txt), [Insights](Insights.txt), and [future ideas](Brainstorming%20Future%20Ideas.txt) for additional project notes.
