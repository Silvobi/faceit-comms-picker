from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_SOURCE = "faceit"


@dataclass(frozen=True)
class CsdaPlayer:
    slot: int
    user_id: int
    name: str
    steam_id: str
    team_key: str
    team_name: str
    team_letter: str


def unsigned_to_signed_32(value: int) -> int:
    value &= 0xFFFFFFFF
    if value & 0x80000000:
        return value - 0x100000000
    return value


def indices_to_mask(indices: Iterable[int]) -> tuple[int, int]:
    low = 0

    for raw_index in indices:
        bit = raw_index - 1
        if bit < 0 or bit > 31:
            raise ValueError(f"Index {raw_index} maps to bit {bit}, outside supported FACEIT range 0..31.")
        low |= 1 << bit

    return low, unsigned_to_signed_32(low)


def command_for_slots(slots: Iterable[int]) -> str:
    _low_u, low_s = indices_to_mask(slots)
    return f"tv_listen_voice_indices {low_s}"


def resolve_csda(explicit_path: str | None) -> Path:
    candidates: list[Path] = []

    if explicit_path:
        candidates.append(Path(explicit_path))

    env_path = os.environ.get("CSDA_EXE")
    if env_path:
        candidates.append(Path(env_path))

    for name in ("csda.exe", "csda"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))

    root = Path.cwd()
    candidates.extend(root.glob("**/csda.exe"))

    temp_root = Path(tempfile.gettempdir())
    candidates.append(
        temp_root
        / "csda-npm-test"
        / "node_modules"
        / "@akiver"
        / "cs-demo-analyzer"
        / "dist"
        / "bin"
        / "windows-x64"
        / "csda.exe"
    )

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    raise FileNotFoundError(
        "Could not find csda.exe. Pass --csda C:\\path\\to\\csda.exe, set CSDA_EXE, "
        "or install @akiver/cs-demo-analyzer locally."
    )


def run_csda(csda: Path, demo_path: Path, output_dir: Path, source: str) -> Path:
    before = {path.resolve() for path in output_dir.glob("*.json")}
    args = [
        str(csda),
        f"-demo-path={demo_path}",
        f"-output={output_dir}",
        "-format=json",
        f"-source={source}",
        "-minify",
    ]
    completed = subprocess.run(args, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        details = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
        raise RuntimeError(f"csda failed for {demo_path} with exit code {completed.returncode}:\n{details}")

    expected = output_dir / f"{demo_path.stem}.json"
    if expected.is_file():
        return expected

    after = [path for path in output_dir.glob("*.json") if path.resolve() not in before]
    if after:
        return max(after, key=lambda path: path.stat().st_mtime)

    all_json = list(output_dir.glob("*.json"))
    if all_json:
        return max(all_json, key=lambda path: path.stat().st_mtime)

    raise FileNotFoundError(f"csda completed, but no JSON export was found in {output_dir}")


def load_csda_players(json_path: Path) -> list[CsdaPlayer]:
    with json_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    raw_players = data.get("players")
    if isinstance(raw_players, dict):
        player_items = raw_players.items()
    elif isinstance(raw_players, list):
        player_items = ((str(index), player) for index, player in enumerate(raw_players))
    else:
        raise ValueError(f"{json_path} has no players object/list")

    players: list[CsdaPlayer] = []
    for fallback_steam_id, player in player_items:
        if not isinstance(player, dict):
            continue
        user_id = player.get("userId")
        if not isinstance(user_id, int):
            continue

        team = player.get("team") if isinstance(player.get("team"), dict) else {}
        team_letter = str(team.get("letter") or "")
        team_name = str(team.get("name") or "")
        team_key = team_letter or team_name or "unknown"
        name = str(player.get("name") or f"Player {user_id + 1}")
        steam_id = str(player.get("steamId") or fallback_steam_id)

        players.append(
            CsdaPlayer(
                slot=user_id + 1,
                user_id=user_id,
                name=name,
                steam_id=steam_id,
                team_key=team_key,
                team_name=team_name,
                team_letter=team_letter,
            )
        )

    return sorted(players, key=lambda player: player.slot)


def group_players(players: Iterable[CsdaPlayer]) -> dict[str, list[CsdaPlayer]]:
    groups: dict[str, list[CsdaPlayer]] = {}
    for player in players:
        groups.setdefault(player.team_key, []).append(player)
    return dict(sorted(groups.items(), key=lambda item: min(player.slot for player in item[1])))


def compare_current_backend(demo_path: Path) -> dict[str, list[int]]:
    from lvig import DemoInspector

    result = DemoInspector.inspect(demo_path)
    groups: dict[str, list[int]] = {}
    for row in result.player_rows:
        slot = row.get("spec_index")
        team = row.get("team") or row.get("team_letter") or row.get("team_name")
        if isinstance(slot, int) and team:
            groups.setdefault(str(team), []).append(slot)

    return {team: sorted(slots) for team, slots in sorted(groups.items(), key=lambda item: min(item[1]))}


def player_key(row: dict[str, Any]) -> str:
    for key in ("steamid", "steam_id", "xuid"):
        value = row.get(key)
        if value not in (None, ""):
            return f"steam:{value}"
    for key in ("name", "player_name", "user_name"):
        value = row.get(key)
        if value not in (None, ""):
            return f"name:{value}"
    return ""


def team_value(row: dict[str, Any]) -> str:
    for key in ("team_name", "team", "side", "team_num"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def print_demo_report(demo_path: Path, json_path: Path, players: list[CsdaPlayer], compare_current: bool) -> None:
    print(f"Demo: {demo_path}")
    print(f"JSON: {json_path}")
    print("Players:")
    for player in players:
        team_label = player.team_letter or player.team_name or "unknown"
        print(f"  slot {player.slot:>2} userId={player.user_id:<2} team={team_label:<12} {player.name}")

    print("Team commands:")
    for team_key, team_players in group_players(players).items():
        slots = [player.slot for player in team_players]
        names = ", ".join(player.name for player in team_players)
        print(f"  {team_key}: {', '.join(map(str, slots))}")
        print(f"    players: {names}")
        print(f"    command: {command_for_slots(slots)}")

    if compare_current:
        print("Current backend comparison:")
        try:
            current_groups = compare_current_backend(demo_path)
        except Exception as exc:
            print(f"  failed: {exc}")
        else:
            csda_slot_sets = sorted(tuple(player.slot for player in team_players) for team_players in group_players(players).values())
            current_slot_sets = sorted(tuple(slots) for slots in current_groups.values())
            status = "MATCH" if csda_slot_sets == current_slot_sets else "DIFF"
            print(f"  status: {status}")
            for team, slots in current_groups.items():
                print(f"  current {team}: {', '.join(map(str, slots))} -> {command_for_slots(slots)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Proof-of-concept cs-demo-analyzer backend for CS2 tv_listen_voice_indices commands."
    )
    parser.add_argument("demos", nargs="+", type=Path, help="One or more .dem files to parse.")
    parser.add_argument("--csda", help="Path to csda.exe. Defaults to CSDA_EXE, PATH, workspace, then prior temp npm test.")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help=f"Analyzer source. Default: {DEFAULT_SOURCE}.")
    parser.add_argument("--output-dir", type=Path, help="Directory for exported JSON. Defaults to a temporary directory.")
    parser.add_argument("--keep-json", action="store_true", help="Keep temporary JSON exports and print their folder.")
    parser.add_argument("--compare-current", action="store_true", help="Also compare slot sets with the current lvig.py backend.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    csda = resolve_csda(args.csda)
    print(f"Using csda: {csda}")

    missing = [path for path in args.demos if not path.is_file()]
    if missing:
        for path in missing:
            print(f"Missing demo: {path}", file=sys.stderr)
        return 2

    if args.output_dir:
        output_dir = args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        cleanup = None
    elif args.keep_json:
        output_dir = Path(tempfile.mkdtemp(prefix="csda-poc-"))
        cleanup = None
    else:
        cleanup = tempfile.TemporaryDirectory(prefix="csda-poc-")
        output_dir = Path(cleanup.name)

    try:
        for index, demo_path in enumerate(args.demos):
            if index:
                print()
            json_path = run_csda(csda, demo_path.resolve(), output_dir, args.source)
            players = load_csda_players(json_path)
            print_demo_report(demo_path.resolve(), json_path.resolve(), players, args.compare_current)
    finally:
        if cleanup is not None:
            cleanup.cleanup()
        elif args.keep_json:
            print(f"\nKeeping JSON exports in: {output_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
