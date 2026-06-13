from __future__ import annotations

import sys
from pathlib import Path

from lvig import DemoInspector, build_auto_team_groups, command_for_indices, indices_to_mask


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: py debug_demo.py <demo.dem>")
        return 2

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Missing file: {path}")
        return 2

    result = DemoInspector.inspect(path)
    rows = [("player_info", row) for row in result.player_rows] + [("ticks", row) for row in result.tick_rows]
    auto_team_groups = build_auto_team_groups(rows)

    print(f"Demo: {path}")
    print(f"Detected slot_start: {result.slot_start}")
    print("Notes:")
    for note in result.notes:
        print(f"  - {note}")

    print("\nPlayers -> spec slots:")
    for row in result.player_rows:
        slot = row.get("spec_index", "")
        name = row.get("name") or row.get("player_name") or ""
        steamid = row.get("steamid") or row.get("steam_id") or row.get("xuid") or ""
        team = row.get("team") or row.get("team_letter") or row.get("team_name") or ""
        print(f"  slot {slot:>2}: {name:<24} steamid={steamid} player_info_team={team}")

    print("\nAuto team groups:")
    for team, indices, players in auto_team_groups:
        low_u, _low_s = indices_to_mask(indices)
        print(f"  {team}: {', '.join(map(str, indices))}")
        print(f"    players: {', '.join(players)}")
        print(f"    command: {command_for_indices(indices)}")
        print(f"    unsigned: {low_u}")

    if len(auto_team_groups) >= 2:
        first_team, first_indices, _first_players = auto_team_groups[0]
        second_team, second_indices, _second_players = auto_team_groups[1]
        print("\nGenerated UI fields:")
        print(f"  Team A ({first_team}) indices: {', '.join(map(str, first_indices))}")
        print(f"  Team A command: {command_for_indices(first_indices)}")
        print(f"  Team B ({second_team}) indices: {', '.join(map(str, second_indices))}")
        print(f"  Team B command: {command_for_indices(second_indices)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
