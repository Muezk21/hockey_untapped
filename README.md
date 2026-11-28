# Hockey Untapped

Hockey Untapped is a hockey event-tracking and analytics project. The current post-game workflow combines NHL play-by-play data with manually recorded zone entries and observations, then exports one CSV containing both sources.

## Current tracker: V4

The current tracker is `v4_stat_tracker.html`. It is a browser-based post-game tool for importing a completed NHL game, reviewing its shots, adding manual observations, classifying shots relative to manually recorded carry-ins, and exporting the combined event log.

### Requirements

- Windows
- Python 3
- A modern browser
- Internet access while loading NHL games and play-by-play

The HTML tracker uses the local Python server as a proxy to the NHL website API. You do not need to install Python packages to run the V4 tracker.

### Start the tracker

Open PowerShell in the project folder:

```powershell
cd "$HOME\OneDrive\Projects\stat_tracker"
py .\nhl_api_server.py
```

Keep that PowerShell window open. In your browser, open:

[http://localhost:8000/](http://localhost:8000/)

The server redirects the root address to `v4_stat_tracker.html`. Do not open the HTML file directly with `file://`; API requests will not work that way.

To stop the server, return to PowerShell and press `Ctrl+C`.

### Import a game

1. Choose the game date. The date field defaults to yesterday.
2. Click **Load Games**.
3. Select the game from the list. If Anaheim is playing, its game is normally preselected.
4. Click **Import Game**.
5. Confirm the teams, score, date, and game ID in the game information line.

The tracker retrieves the NHL play-by-play and normalizes shot attempts, goals, takeaways, giveaways, penalties, and game-state reset events. Shot rows include the shooter when roster data is available, shot type, result, strength situation, event ID, and rink coordinates when supplied by the NHL.

The team dropdown lets you choose which of the two teams you are analyzing. The default is Anaheim (ANA). The opponent field updates automatically.

### Record manual observations

The NHL play-by-play supplies the game events and shot timestamps. You supply the game clock for your manual observations: enter the clock as shown on the footage, choose the period, and then use the buttons or hotkeys below.

Click **Start Tracking (enable hotkeys)** to turn on keyboard shortcuts. Hotkeys are inactive until tracking is enabled. The clock field accepts `MM:SS`; press Enter after editing it to return focus to the tracker. The period, team, and game selectors also drop focus after a selection.

**Zone entry**

| Key | Observation |
|---|---|
| `I` | Carry-in — record only when the analyzed team carries the puck across the offensive blue line |

A carry-in is the timing anchor for the shot classification. Do not record dump-ins or uncontrolled entries as carry-ins. Record the carry-in at the moment the puck is carried across the offensive blue line, regardless of whether the play developed from a transition, stretch pass, regroup, or another route.

**Other manual events**

| Key | Event |
|---|---|
| `3` | DZ → OZ Transition Completed |
| `4` | Stretch Pass → OZ Possession |
| `1` | DZ Blueline Play Shut Down |
| `2` | D-Man Aggressive Gap Close |
| `=` | OZ Turnover Forced |
| `A` | Activated D-Man (OZ) |
| `L` | Lost Possession |

The transition and stretch-pass events are separate observations; neither is itself a zone entry and neither starts the shot-timing clock. The gap-close event is also an observation, not a carry-in.

**Mark the last manually logged event**

| Key | Tag |
|---|---|
| `S` | Scoring Chance |
| `P` | Penalty Drawn |
| `G` | Led To Goal |
| `Backspace` | Undo the last manually logged item |

These modifiers apply to the most recently logged manual event, not to a selected NHL shot.

### Review and tag NHL shots

The shot table is populated from NHL play-by-play. Click a shot row to select it; the selected row is highlighted. The detail panel explains the shot's classification and why it received that classification.

| Key | Tag on the selected shot |
|---|---|
| `C` | Scoring Chance |
| `8` | 2nd Chance |
| `9` | 3rd+ Chance |
| `0` | Shot With Traffic |
| `-` | Low-Value Shot |
| `↑` / `↓` | Select previous / next visible shot |
| `Esc` | Deselect the shot |

The 2nd Chance and 3rd+ Chance tags automatically mark the shot as a scoring chance. Selecting either clears the other. Clearing the Scoring Chance tag also clears the 2nd/3rd+ tag.

The table filters can show only the analyzed team or only 5v5 shots. These filters affect the displayed shot list, not the underlying imported data or CSV export.

### How shot classification works

Shot timing is measured from the most recent manually recorded carry-in by the team being analyzed—not from the start of a possession, a transition, or a stretch pass.

| Classification | Time from carry-in |
|---|---:|
| Rush | Under 5 seconds |
| Early | 5–10 seconds, inclusive |
| Sustained | Over 10 seconds through 30 seconds |
| Extended | Over 30 seconds |

Additional rules:

- The first shot after a carry-in is assigned a timing class.
- Later shots in that same possession are classified as **Follow-up** and are not assigned a new timing class.
- If possession begins but no carry-in is recorded before the first shot, the shot is **Unclassified**. The tracker does not invent an entry.
- A shot recorded before the carry-in time is **Unclassified** and the detail panel flags the clock discrepancy.
- A takeaway or giveaway can start or end the analyzed team's possession, based on which team made the play. It does not count as a carry-in.
- An opponent shot, a goal, a faceoff, a stoppage, a period boundary, or the end of the game resets the current possession/timing context.
- Manually logging `L`, `=`, or `1` ends or resets the relevant possession context as defined by the tracker. `=` and `1` start a new possession context, but do not provide a carry-in time.
- Only the selected team's manual entries and events are used in its classification. Switch the team dropdown to analyze the other team.

Use the explanation under each selected shot to audit the exact entry, possession start, reset, and elapsed time used by the tracker.

### Saving and exporting

- Manual carry-ins, manual events, shot tags, and the selected team are automatically saved in the browser's local storage, separately for each game.
- Re-importing the same game in the same browser restores its saved session.
- Saved sessions are local to that browser and computer; they are not uploaded to GitHub or synchronized between devices.
- **Edit** and **Delete** are available for each manual entry and event.
- **Undo** removes the last manually logged entry or event.
- **Clear saved session** deletes the saved manual entries, events, and shot tags for the currently imported game after confirmation.
- Click **Export CSV** to download the combined NHL and manual event log for the imported game.

The CSV includes source, game metadata, NHL event IDs, shot details, possession classification, seconds since entry/possession start, manual tags, rink coordinates, elapsed time, and notes explaining classifications. NHL-sourced rows are marked `NHL API`; manual rows are marked `Manual`. The export is sorted in game order.

## Local NHL API proxy

`nhl_api_server.py` uses only the Python standard library. It serves the project folder and proxies these requests to the NHL web API:

| Local route | NHL endpoint |
|---|---|
| `/api/score/now` | `/v1/score/now` |
| `/api/score/YYYY-MM-DD` | `/v1/score/YYYY-MM-DD` |
| `/api/game/{game_id}/landing` | `/v1/gamecenter/{game_id}/landing` |
| `/api/game/{game_id}/play-by-play` | `/v1/gamecenter/{game_id}/play-by-play` |

The proxy listens on `127.0.0.1:8000`. These are public NHL website endpoints, not a guaranteed stable, officially supported developer API. NHL response fields and availability may change.

### Troubleshooting

- **The page says it cannot reach the local server:** confirm the PowerShell window running `py .\nhl_api_server.py` is still open.
- **The browser cannot load games:** make sure you opened `http://localhost:8000/`, not the HTML file directly, and that you have internet access.
- **No games appear:** verify the selected date; the NHL may have no games scheduled that day.
- **A player appears as an ID:** the play-by-play response did not include the roster information needed to resolve that player's name.
- **A shot is unclassified:** select it and read the explanation. A carry-in may not have been recorded, a reset may have occurred, or the clock may be inconsistent.


## Product direction and current development plan

Hockey Untapped's differentiator is its custom hockey-event framework, not a generic NHL statistics dashboard. The project is evaluating whether these events reveal useful information about defensive execution, transitions, possession, and offensive pressure that standard box-score and play-by-play statistics do not capture.

The current approach is a hybrid system:

1. **NHL play-by-play API:** automatically imports observable official events such as shots, goals, penalties, takeaways, giveaways, and available event details.
2. **Custom event layer:** preserves Hockey Untapped observations such as entry denials, defensive gap closes, transitions, stretch-pass possessions, forced turnovers, activated defensemen, and manually judged shot descriptors.
3. **Video/computer-vision layer (research stage):** investigate whether broadcast video can help detect player movement, puck location, possession changes, and selected custom events. Computer vision must supplement and validate the custom-event definitions; it must not silently replace them with generic event labels.
4. **Combined analysis:** link custom events to subsequent API events and outcomes when the game, period, timing, team, and sequence support a defensible link. Report association, not causation.

### Preliminary custom-metric audit

The following are **initial design assessments**, not measured reliability scores. They are based on the current definitions and the likely information available from the API/video. Scores are 1 (weak) to 5 (strong).

- **Definition:** Is the event specific enough to apply?
- **Value:** Could it reveal something useful beyond ordinary statistics?
- **Consistency:** Is it likely that two reviewers could agree? This is provisional until independently coded video is compared.
- **Outcome:** Can it be linked to meaningful subsequent events or results?
- **Automation:** How feasible is API/video-assisted detection?

| Metric | Definition | Value | Consistency | Outcome | Automation |
|---|---:|---:|---:|---:|---:|
| Entry Denial | 3 | 4 | 3 | 4 | 3 |
| D-Man Gap Close | 3 | 4 | 2 | 4 | 3 |
| DZ → OZ Transition Completed | 4 | 4 | 4 | 4 | 4 |
| Stretch Pass → OZ Possession | 3 | 3 | 2 | 4 | 2 |
| Controlled Carry-in | 5 | 4 | 4 | 4 | 4 |
| Forced OZ Turnover | 3 | 4 | 2 | 4 | 3 |
| Activated Defenseman | 3 | 3 | 2 | 3 | 3 |
| Lost Possession | 3 | 3 | 3 | 3 | 3 |
| Rush / Early / Sustained / Extended Shot | 5 | 4 | 4 | 4 | 5 |
| Scoring Chance | 2 | 5 | 2 | 5 | 2 |
| Second / Third+ Chance | 4 | 4 | 3 | 4 | 3 |
| Traffic | 2 | 3 | 2 | 3 | 2 |
| Low-Value Shot | 2 | 2 | 2 | 3 | 3 |

These scores are a prioritization aid, not proof that a metric works. In particular, **Consistency** must be tested by having two people independently label the same sample of clips using written definitions, then comparing agreement and resolving disagreements. **Outcome** must be tested on multiple games with sufficient observations and valid links. A high theoretical value score does not establish predictive power.

### Current computer-vision feasibility

Computer vision is a Python software-development effort, not a single program that automatically understands hockey. The likely building blocks are:

- Python 3 and Visual Studio Code for development.
- FFmpeg for reading, trimming, and extracting frames from video files.
- OpenCV for video/frame processing and rink-coordinate mapping.
- PyTorch for running machine-learning models.
- Ultralytics YOLO for player/object detection experiments.
- Supervision and ByteTrack for detection visualization and tracking objects across frames.

Do not install or train a large model until a usable video input is confirmed. The current video access is full-game streams available approximately 24 hours after games; downloadable local video files are not currently available. A stream being watchable does not mean it can be downloaded or processed as a file. First determine whether the provider offers an authorized download or replay file and whether its terms permit local analysis. Do not attempt to bypass DRM or access controls. If only a browser stream is available, the initial experiment may need to use permitted short clips or manually captured review segments rather than automated full-game ingestion.

The hardest computer-vision problems are reliable puck localization, possession attribution, player identity across camera cuts, and interpreting intent/context. Player detection and approximate movement tracking are more approachable starting points. Any inferred event should retain its source and confidence and be reviewable by a person.

### Next steps

1. **Audit the custom metrics:** finalize plain-language definitions, inclusion/exclusion examples, and edge cases. Remove overlap or ambiguity before automating.
2. **Collect outside feedback:** ask coaches, players, analysts, and knowledgeable hockey viewers which events are useful, missing, or too subjective.
3. **Run a consistency test:** select a small set of representative clips and have two reviewers independently label the same events. Compare agreement before treating subjective metrics as dependable.
4. **Confirm video access:** identify the stream provider's replay/download options and permitted use. Obtain a short local video file or authorized clip for a proof of concept.
5. **Build a narrow computer-vision prototype:** start with player detection/tracking and rink-position estimation on a short clip. Then test one event, preferably D-Man Gap Close or a zone transition. Do not attempt every metric at once.
6. **Continue API automation:** automate game selection/import and reliable NHL event metrics while keeping manual custom observations intact.
7. **Join and validate:** link custom events to NHL API events by game, period, timestamp, team, and event/sequence context. Keep uncertain links separate.
8. **Produce a combined report:** show API statistics, custom-event counts, linked outcomes, data coverage, and confidence/limitations. Preserve legacy manual data as a separate cohort.

### What evidence is needed to validate the metrics?

A preliminary definition/value/automation audit can be done now. Empirical validation needs more evidence:

- **Consistency:** independently label the same clips; measure agreement per event, not just total event counts.
- **Outcome:** accumulate repeated events across multiple games and compare outcomes against an appropriate baseline or comparison group.
- **Predictive value:** wait for a substantially larger multi-game dataset, use held-out games for testing, and check calibration. Do not make predictive claims from small samples.
- **Automation accuracy:** compare model detections with human-reviewed labels, reporting precision, recall, and false positives/negatives for each event.

The existing 16-game legacy cohort and the small V4 test exports are useful for development and historical context, but they do not validate every custom metric. Legacy manually assigned timing labels must remain separate from V4 timing measured from recorded carry-ins.

## OCR tracker (separate experimental tool)

The OCR tool is separate from the V4 HTML tracker. It reads the broadcast clock and period from configured screen regions and logs hotkey events to CSV. It is not required for the NHL API tracker.

### OCR requirements

- Python 3 on Windows
- Tesseract OCR installed separately
- Python packages:

```powershell
py -m pip install Pillow pytesseract keyboard
```

The script currently expects Tesseract at:

```text
C:\Program Files\Tesseract-OCR\tesseract.exe
```

If Tesseract is installed elsewhere, update `pytesseract.pytesseract.tesseract_cmd` in `OCR Tracker/ocr_tracker.py`.

### Run the OCR tracker

From the project folder:

```powershell
py ".\OCR Tracker\ocr_tracker.py"
```

Choose a broadcast configuration, choose the team, enter the opponent and game date, position the video, and press Enter to start. Press `Esc` to stop tracking and export the logged events. Broadcast clock and period capture regions are stored in `OCR Tracker/broadcast_configs.json`; these screen coordinates need to match the layout and screen on which the broadcast is displayed.

The OCR tool uses global keyboard listening and screen capture. Run it only when you intend to track a game, and ensure the selected broadcast configuration matches your video layout.

## Project notes and supporting material

The repository also contains historical tracker versions, OCR calibration images/configurations, game CSV exports, and analysis material. Older tracker files are retained for reference; use `v4_stat_tracker.html` as the current NHL API-connected tracker.

For project metric definitions and research notes, see:

- [Metrics definitions](Metrics%20definitions.txt)
- [Insights](Insights.txt)
- [Future ideas](Brainstorming%20Future%20Ideas.txt)
