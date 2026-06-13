# FACEIT Comms Picker

Small Python GUI for generating `tv_listen_voice_indices` commands for CS2 demo voice playback.

## Run

Install dependencies:

```powershell
py -m pip install -r requirements.txt
```

The parser backend is `cs-demo-analyzer`. The app auto-detects `csda.exe` from:

- `CSDA_EXE`
- `PATH`
- a `csda.exe` somewhere inside this project folder
- the previous local npm test install under `%TEMP%\csda-npm-test`

Launch:

```powershell
py lvig.py
```

## Current workflow

1. Choose or drop the folder where your FACEIT `.dem` files are stored.
2. Pick a demo from the detected demo list.
3. The app parses the demo automatically.
4. It exports `cs-demo-analyzer` JSON.
5. It maps each player with `spec_player slot = userId + 1`.
6. It generates separate commands for Team A and Team B on the **Commands** tab.
7. Press **Copy command** under either team and paste into the CS2 console.

The tool uses CS2's one-based slot mapping where slot `1` sets bit `0`, slot `2` sets bit `1`, and so on.

## Manual correction

If a demo parses oddly, use the **Manual correction** tab:

- Select player rows in the parsed details table.
- Press **Add selected to Team A**, **Add selected to Team B**, or **Add selected to Custom**.
- Press **Generate** to refresh commands.

Drag-and-drop accepts either a folder or a `.dem` file. Dropping a `.dem` file loads its parent folder and selects that demo.

## Settings

The **Settings** tab includes:

- Theme: `System`, `Light`, or `Dark` (`System` by default)
- Show parsed demo details: off by default

The drop area shows parser state:

- Gray: waiting for a demo
- Yellow/orange: parsing
- Green: parsed successfully
- Red: parsing failed

## Debugging

To print every intermediate mapping for a demo:

```powershell
py debug_demo.py "C:\path\to\demo.dem"
```

This shows:

- detected `spec_player` slots from `cs-demo-analyzer`
- player rows and teams used for grouping
- final team indices and commands

To test the `cs-demo-analyzer` proof-of-concept backend without changing the GUI:

```powershell
py csda_poc.py --compare-current "C:\path\to\demo.dem"
```

The proof script runs `csda.exe`, exports minified JSON, maps `slot = userId + 1`, groups by team, and prints the generated `tv_listen_voice_indices` commands.
