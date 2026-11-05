# FACEIT Comms Picker (LVIG)

LVIG generates `tv_listen_voice_indices` console commands for listening to selected players in FACEIT CS2 demos. Load a demo to get commands for both teams, or enter player slots yourself in **Raw Convertion**.

Current source version: **v0.2.0-poc**. This is a Windows proof of concept designed for FACEIT demos with recorded voice communication. Other demo sources are not verified.

## Run on Windows

### From source

Install [Python](https://www.python.org/downloads/windows/) and [Git](https://git-scm.com/downloads/win), then run:

```powershell
git clone https://github.com/Silvobi/faceit-comms-picker.git
cd faceit-comms-picker
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe lvig.py
```

The application is tested with Python 3.14 and PySide6. The repository includes the Windows `cs-demo-analyzer` executable under `vendor/cs-demo-analyzer/`; a separate Node.js or Go installation is not needed.

### Packaged builds

Available Windows builds are listed on the [Releases page](https://github.com/Silvobi/faceit-comms-picker/releases). Download the Windows ZIP for the release you want, extract it, and run `FACEIT-Comms-Picker.exe`. Packaged builds include Python, Qt, and the demo parser, so users do not need to install Python or dependencies.

Release downloads have their own version numbers. Use the source instructions above to run the version documented on this branch.

## Generate team commands from a demo

1. Open the **Commands** tab.
2. Click the drop area and choose a `.dem` file, or drag a demo onto it. The application starts parsing that file automatically.
3. To browse several demos, click **Choose folder**, select their folder, and choose a demo from the list. **Refresh** rescans the folder.
4. Check the player lists shown under **Team A** and **Team B**.
5. Click **Copy command** for the team you want to hear.
6. Open the same demo in CS2 and paste the copied command into the developer console.

You can also drop a folder onto the drop area. Choosing or dropping a demo loads its parent folder into the demo list. The application remembers the last selected folder.

**Team A** and **Team B** follow the parser's grouping order; they do not necessarily match FACEIT's team labels. Use the displayed player names to identify the team you want.

The drop area indicates parsing status: gray while idle, yellow while parsing, green after success, and red if parsing fails. If parsing fails or a player is assigned incorrectly, use **Raw Convertion** with slots checked in CS2.

## Convert slots with Raw Convertion

This tab works without loading a demo into LVIG or running the parser.

1. Open your FACEIT demo in CS2 and open the developer console.
2. Enter `spec_player 1`, then try `spec_player 2`, `spec_player 3`, and so on. Check which player each number selects.
3. Enter the exact numbers that select the players you want to hear into the five numeric fields. Slots range from **1 to 32**; type a number, use the arrows, or scroll the mouse wheel over a field.
4. Leave unused fields at **—**. You can convert fewer than five players, and repeated slots count once.
5. Click **Convert to command**, then **Copy command**.
6. Paste the command into the CS2 developer console while playing that demo.

Example:

```text
Player slots: 1, 4, 5, 7, 8
Command:     tv_listen_voice_indices 217
```

Use the numbers from `spec_player x` directly; do not subtract one yourself. Editing a field clears the previous result until you convert again. **Clear** resets the five fields and their result. Raw conversions do not change the team commands on the **Commands** tab.

## Settings and About

- **Theme:** follow the system appearance or select Light or Dark.
- **Show parsed demo details:** display player slots, names, Steam IDs, teams, user IDs, and parser data on the **Commands** tab. This is off by default.
- **Auto-fill teams:** regenerate the team cards from the parsed data when the details panel is visible.
- **About:** view the application version, project links, and the bundled parser's license.

The tabs fill the window width. The raw converter can scroll vertically when the window is too small to show its instructions at once.

## Parser configuration

LVIG uses [akiver/cs-demo-analyzer](https://github.com/akiver/cs-demo-analyzer) to export player data from a demo. It maps each player's `userId + 1` to the slot used by `spec_player` and combines selected slots into a 32-bit voice mask. Slot 1 sets bit 0; slot 32 sets bit 31. A negative command value is valid when the signed mask includes slot 32.

The bundled parser is normally found automatically. To use another executable, set `CSDA_EXE` before starting the application:

```powershell
$env:CSDA_EXE = 'C:\tools\cs-demo-analyzer\csda.exe'
.\.venv\Scripts\python.exe lvig.py
```

For source runs, the application also searches `PATH` and the project directory. Packaged Windows builds check their bundled parser first. The parser's MIT license is included at [`vendor/cs-demo-analyzer/LICENSE.md`](vendor/cs-demo-analyzer/LICENSE.md).

## Tests and diagnostics

Run the GUI regression tests with isolated settings and offscreen rendering:

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_lvig
```

Print the parsed player data, detected slots, team grouping, and generated commands for a demo:

```powershell
.\.venv\Scripts\python.exe debug_demo.py 'C:\path\to\demo.dem'
```

For just the team commands:

```powershell
.\.venv\Scripts\python.exe lvig.py --debug-demo 'C:\path\to\demo.dem'
```

## Platform support

Windows is the supported platform for this proof of concept. The repository bundles a Windows parser executable and does not currently provide a Windows installer or a tested Linux package.
