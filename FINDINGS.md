# Findings

## Confirmed command conversion

`tv_listen_voice_indices` uses one-based slot numbers mapped to zero-based bits:

```text
slot 1 -> bit 0
slot 2 -> bit 1
slot 3 -> bit 2
...
```

Example:

```text
slots: 1, 4, 5, 7, 8
mask:  217
```

The generated paste format is:

```text
tv_listen_voice_indices <mask>
```

## Confirmed slot extraction

`cs-demo-analyzer` exposes each player's `userId`. In its source, `userId + 1` maps to the in-game `spec_player` slot:

```text
real spec_player slot = userId + 1
```

This replaced the earlier `demoparser2` plus raw `userinfo` offset approach, which worked on some demos but failed on at least one verified test demo.

## Verified demos

Seven demos have been manually verified in CS2 with the `cs-demo-analyzer` backend:

- `bileysThingOnAnubis.dem`
- `test1ancient.dem`
- all five demos in `game\csgo\test demos`

### bileysThingOnAnubis.dem

Path:

```text
C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\bileysThingOnAnubis.dem
```

Known manual slots:

```text
3  - Matve926
4  - BongoOG
5  - klapek1232
6  - xWaiFx
7  - npolanskiy
8  - AkeAlkan
9  - BlackMonkey_
10 - ossuruklu1
11 - twizinho
12 - Bekoood
```

Confirmed app output:

```text
CT:        3, 4, 5, 7, 9  -> tv_listen_voice_indices 348
TERRORIST: 6, 8, 10, 11, 12 -> tv_listen_voice_indices 3744
```

### test1ancient.dem

Path:

```text
C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\test1ancient.dem
```

Status:

```text
Manually tested in CS2.
Spec_player slot assignment was correct.
Generated tv_listen_voice_indices commands were correct.
```

## Current known risk

The app labels output as Team A / Team B based on detected team grouping order, not FACEIT's visual Team A / Team B labels.

Use the player lists shown under each command to confirm which side the command represents.

## Debug command

Use this to print the full internal mapping:

```powershell
py debug_demo.py "C:\path\to\demo.dem"
```

It prints:

- detected `spec_player` slots from `cs-demo-analyzer`
- player rows and teams used for grouping
- final indices and commands
