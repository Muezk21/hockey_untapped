# Hockey Untapped

Hockey Untapped is a hockey tracking and analytics project combining manually observed events with NHL game data and analysis scripts.

## Project areas

- **HTML event tracker:** Browser-based interface for selecting teams, entering game details, recording events with hotkeys, tagging outcomes, and exporting CSV.
- **OCR experiments:** `OCR Tracker/ocr_tracker.py` and its calibration/diagnostic tools explore automatic clock and period capture from a scoreboard. This is separate from the HTML event tracker.
- **NHL data exploration:** `nhl_probe.py` and live API tests query NHL web endpoints for schedules, game state, clock, and play-by-play.
- **Data processing and analysis:** `preprocess_events.py`, `master_data_script.py`, `analytics.py`, and `dman_impact.py` support data preparation and analysis.
- **Data:** `raw_data/`, `enriched_data/`, `analytics_reports/`, and `master_dataset.csv` contain tracking and analysis outputs. Older material is kept under `archive/`.

## HTML event tracker

The current HTML/JavaScript tracker supports team, opponent, date, period, and game-clock fields; keyboard event logging; scoring-chance, penalty, and goal tags; optional shot-result selection; undo; and CSV export.

Current event hotkeys:

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

Modifiers apply to the most recently logged event: `s` = scoring chance, `p` = penalty drawn, `g` = led to goal. `Backspace` undoes the last event. The CSV contains team, game clock, period, event, outcome flags, and shot result.

The HTML tracker currently relies on manually supplied game-clock and period values. The goal of the API work is to populate these automatically without disrupting the existing event workflow or CSV output.

## Setup and OCR tools

The Python OCR experiments use Python 3 on Windows. Install the packages used by the OCR tracker with:

```powershell
python -m pip install Pillow pytesseract keyboard
```

Install the Tesseract OCR application separately and ensure its executable path matches the setting in `OCR Tracker/ocr_tracker.py`.

Run the OCR tracker from the project directory:

```powershell
python "OCR Tracker/ocr_tracker.py"
```

The OCR tools are experimental and are not required for the HTML event tracker.

## Recent development notes (November 23–25, 2026)

- Set up and tested Python OCR dependencies and configured Tesseract separately.
- Built and tested broadcast-specific screen regions for clock and period capture. Screen-coordinate troubleshooting included moving the game feed to the primary monitor.
- Diagnosed inconsistent OCR clock recognition. A manual image-preprocessing test successfully read `18:02`, but that preprocessing was not integrated into the OCR tracker.
- Identified an OCR reliability issue: failed reads can leave the previous clock value in place, creating potentially stale timestamps.
- Continued NHL API exploration using the public NHL web endpoints.
- Successfully retrieved the current scoreboard from `/v1/score/now`, identified live games and game IDs, and fetched a live game's landing data.
- Live-tested `/v1/gamecenter/{game_id}/landing`. The response provided game status, period, time remaining, seconds remaining, clock-running state, intermission state, score, and shots on goal.
- Confirmed a live clock sample for Utah @ Minnesota (game ID `2026020396`): the API returned period 2, 08:36 remaining, `running: true`, and `inIntermission: false`. This validates API clock retrieval during live play; broader reliability and update-cadence testing remain outstanding.

## Next development steps

1. Inspect live play-by-play from `/v1/gamecenter/{game_id}/play-by-play` and catalogue which events, players, teams, timestamps, and rink details are available.
2. Compare API events with the HTML tracker's manual categories. Identify which events can be automated reliably and which still require human observation.
3. Build a small standalone API test before integrating anything into the HTML tracker.
4. Once validated, connect the API clock and period to the HTML tracker while preserving its hotkeys, event definitions, outcome tags, undo, and CSV format.
5. Reassess the event taxonomy based on the data available and the defensive-performance questions Hockey Untapped is intended to answer.

## NHL API endpoints and caveats

- `https://api-web.nhle.com/v1/score/now` — current scoreboard and game IDs.
- `https://api-web.nhle.com/v1/gamecenter/{game_id}/landing` — game state, clock, period, score, and other game summary data.
- `https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play` — event-level game timeline.

These are publicly accessible NHL website endpoints, not a guaranteed stable, officially supported developer API. Validate response fields, update cadence, and reliability before depending on them.

## Important metric notes

- Possession starts: `1` (DZ blue-line shutdown) and `=` (forced OZ turnover).
- Puck movement while already in possession: `3` (DZ → OZ transition) and `4` (stretch pass → OZ possession).
- D-man actions: `2` (aggressive gap close) and `a` (activated D-man in OZ).
- Timed-shot keys `5`, `6`, `7`, and `x` are measured from zone entry, not possession start.
- Modifiers `s`, `p`, and `g` apply to the last logged event.

See [Metrics definitions](Metrics%20definitions.txt), [Insights](Insights.txt), and [future ideas](Brainstorming%20Future%20Ideas.txt) for additional project notes.
