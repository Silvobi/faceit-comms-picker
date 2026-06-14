from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from PySide6 import QtCore, QtGui, QtWidgets


APP_TITLE = "FACEIT Comms Picker"
UI_FONT_FAMILY = "Helvetica"
UI_FONT_FALLBACK = "Segoe UI"
MONO_FONT_FAMILY = "Consolas"
SETTINGS_ORG = "FaceitCommsPicker"
SETTINGS_APP = "FaceitCommsPicker"
SETTINGS_DEMO_FOLDER = "demoFolder"
SETTINGS_THEME_MODE = "themeMode"
SETTINGS_SHOW_DETAILS = "showParsedDetails"


@dataclass(frozen=True)
class Theme:
    accent: str
    accent_dark: str
    bg: str
    border: str
    card: str
    code_bg: str
    drop_bg: str
    drop_border: str
    drop_error_bg: str
    drop_error_border: str
    drop_idle_bg: str
    drop_idle_border: str
    drop_parsing_bg: str
    drop_parsing_border: str
    drop_success_bg: str
    drop_success_border: str
    header: str
    input_bg: str
    input_readonly: str
    muted: str
    selection: str
    tab: str
    text: str


LIGHT_THEME = Theme(
    accent="#247a52",
    accent_dark="#1f6847",
    bg="#f3f5f7",
    border="#d8dde3",
    card="#ffffff",
    code_bg="#f7f9fb",
    drop_bg="#eaf4ee",
    drop_border="#8fc7a7",
    drop_error_bg="#fdecec",
    drop_error_border="#d95f5f",
    drop_idle_bg="#eef1f4",
    drop_idle_border="#c7ced6",
    drop_parsing_bg="#fff4d6",
    drop_parsing_border="#d99b24",
    drop_success_bg="#eaf4ee",
    drop_success_border="#8fc7a7",
    header="#e9edf2",
    input_bg="#ffffff",
    input_readonly="#f7f9fb",
    muted="#5f6b7a",
    selection="#d8eadf",
    tab="#e9edf2",
    text="#17202a",
)

DARK_THEME = Theme(
    accent="#2fa66f",
    accent_dark="#23875a",
    bg="#171b20",
    border="#343b45",
    card="#20262d",
    code_bg="#151a1f",
    drop_bg="#1c2b25",
    drop_border="#347557",
    drop_error_bg="#351f24",
    drop_error_border="#d36a6a",
    drop_idle_bg="#20262d",
    drop_idle_border="#47515d",
    drop_parsing_bg="#342d1c",
    drop_parsing_border="#d09a38",
    drop_success_bg="#1c2b25",
    drop_success_border="#347557",
    header="#252c34",
    input_bg="#151a1f",
    input_readonly="#14181d",
    muted="#a5afba",
    selection="#254735",
    tab="#252c34",
    text="#eef2f5",
)


def system_uses_light_theme() -> bool:
    if sys.platform == "win32":
        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _value_type = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return bool(value)
        except OSError:
            pass

    palette = QtWidgets.QApplication.palette()
    window_color = palette.color(QtGui.QPalette.ColorRole.Window)
    return window_color.lightness() >= 128


def current_theme(mode: str = "system") -> Theme:
    if mode == "light":
        return LIGHT_THEME
    if mode == "dark":
        return DARK_THEME
    return LIGHT_THEME if system_uses_light_theme() else DARK_THEME


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


def command_for_indices(indices: Iterable[int]) -> str:
    _low_u, low_s = indices_to_mask(indices)
    return f"tv_listen_voice_indices {low_s}"


def parse_index_text(text: str) -> list[int]:
    normalized = text.replace("\n", ",").replace(";", ",").replace(" ", ",")
    values: list[int] = []
    for part in normalized.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text.strip())
            end = int(end_text.strip())
            step = 1 if end >= start else -1
            values.extend(range(start, end + step, step))
        else:
            values.append(int(part))
    return sorted(set(values))


def compact_value(value: Any, limit: int = 70) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "..."


@dataclass
class DemoInspection:
    player_rows: list[dict[str, Any]]
    tick_rows: list[dict[str, Any]]
    notes: list[str]
    slot_start: int = 1


class DemoInspector:
    DEFAULT_SOURCE = "faceit"

    @staticmethod
    def inspect(path: Path) -> DemoInspection:
        notes: list[str] = []
        csda = DemoInspector.resolve_csda()
        notes.append(f"Using cs-demo-analyzer: {csda}")

        with tempfile.TemporaryDirectory(prefix="lvig-csda-") as output_dir_text:
            json_path = DemoInspector.run_csda(csda, path, Path(output_dir_text))
            player_rows = DemoInspector.load_player_rows(json_path)

        if not player_rows:
            notes.append("cs-demo-analyzer exported no players.")
            return DemoInspection(player_rows=[], tick_rows=[], notes=notes, slot_start=1)

        slot_start = min(int(row["spec_index"]) for row in player_rows)
        notes.append(f"Loaded {len(player_rows)} players from cs-demo-analyzer JSON.")
        notes.append("Spec slots use cs-demo-analyzer userId + 1.")
        return DemoInspection(player_rows=player_rows, tick_rows=[], notes=notes, slot_start=slot_start)

    @staticmethod
    def resolve_csda() -> Path:
        candidates: list[Path] = []

        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            candidates.append(Path(bundle_root) / "vendor" / "cs-demo-analyzer" / "csda.exe")

        env_path = os.environ.get("CSDA_EXE")
        if env_path:
            candidates.append(Path(env_path))

        for name in ("csda.exe", "csda"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))

        root = Path(__file__).resolve().parent
        candidates.append(root / "vendor" / "cs-demo-analyzer" / "csda.exe")
        candidates.extend(root.glob("**/csda.exe"))

        candidates.append(
            Path(tempfile.gettempdir())
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
            "Could not find csda.exe. Set CSDA_EXE to the cs-demo-analyzer binary, "
            "put csda.exe next to this app, or install @akiver/cs-demo-analyzer locally."
        )

    @staticmethod
    def run_csda(csda: Path, demo_path: Path, output_dir: Path) -> Path:
        args = [
            str(csda),
            f"-demo-path={demo_path}",
            f"-output={output_dir}",
            "-format=json",
            f"-source={DemoInspector.DEFAULT_SOURCE}",
            "-minify",
        ]
        completed = subprocess.run(args, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            details = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
            raise RuntimeError(f"cs-demo-analyzer failed with exit code {completed.returncode}:\n{details}")

        expected = output_dir / f"{demo_path.stem}.json"
        if expected.is_file():
            return expected

        exports = list(output_dir.glob("*.json"))
        if exports:
            return max(exports, key=lambda export: export.stat().st_mtime)

        raise FileNotFoundError(f"cs-demo-analyzer completed, but no JSON export was found in {output_dir}.")

    @staticmethod
    def load_player_rows(json_path: Path) -> list[dict[str, Any]]:
        with json_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        raw_players = data.get("players")
        if isinstance(raw_players, dict):
            player_items = raw_players.items()
        elif isinstance(raw_players, list):
            player_items = ((str(index), player) for index, player in enumerate(raw_players))
        else:
            raise ValueError("cs-demo-analyzer JSON has no players object/list.")

        rows: list[dict[str, Any]] = []
        for fallback_steam_id, player in player_items:
            if not isinstance(player, dict):
                continue
            user_id = player.get("userId")
            if not isinstance(user_id, int):
                continue

            team = player.get("team") if isinstance(player.get("team"), dict) else {}
            team_letter = str(team.get("letter") or "")
            team_name = str(team.get("name") or "")
            spec_index = user_id + 1
            rows.append(
                {
                    "spec_index": spec_index,
                    "user_id": user_id,
                    "name": str(player.get("name") or f"Player {spec_index}"),
                    "steamid": str(player.get("steamId") or fallback_steam_id),
                    "team": team_letter or team_name or "unknown",
                    "team_letter": team_letter,
                    "team_name": team_name,
                }
            )
        return sorted(rows, key=lambda row: int(row["spec_index"]))


def team_value(row: dict[str, Any]) -> str:
    for key in ("team", "team_letter", "team_name", "side", "team_num"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def build_auto_team_groups(rows: list[tuple[str, dict[str, Any]]]) -> list[tuple[str, list[int], list[str]]]:
    players_by_team: dict[str, list[tuple[int, str]]] = {}
    for source, row in rows:
        if source != "player_info":
            continue
        spec = int(row.get("spec_index", 0))
        if spec <= 0:
            continue
        team = team_value(row)
        if not team or team == "unknown":
            continue
        name = compact_value(row.get("name") or row.get("player_name") or f"Player {spec}")
        players_by_team.setdefault(team, []).append((spec, name))

    return sorted(
        (
            (
                team,
                [spec for spec, _name in sorted(players, key=lambda item: item[0])],
                [name for _spec, name in sorted(players, key=lambda item: item[0])],
            )
            for team, players in players_by_team.items()
        ),
        key=lambda item: min(item[1]) if item[1] else 999,
    )


class ParserWorker(QtCore.QThread):
    completed = QtCore.Signal(object, object, int, object)
    failed = QtCore.Signal(str, bool)

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path

    def run(self) -> None:
        try:
            result = DemoInspector.inspect(self.path)
            rows = [("player_info", row) for row in result.player_rows]
            rows.extend(("ticks", row) for row in result.tick_rows)
            self.completed.emit(rows, result.notes, result.slot_start, self.path)
        except FileNotFoundError as exc:
            self.failed.emit(str(exc), True)
        except Exception as exc:
            self.failed.emit(str(exc), False)


class DropArea(QtWidgets.QFrame):
    path_dropped = QtCore.Signal(Path)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setObjectName("dropArea")
        self.setProperty("state", "idle")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(6)

        icon = QtWidgets.QLabel("[.dem]")
        icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        icon.setObjectName("dropIcon")
        self.label = QtWidgets.QLabel("Drop a demo folder here or click to choose one")
        self.label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setObjectName("dropLabel")

        layout.addWidget(icon)
        layout.addWidget(self.label)

    def set_state(self, state: str, text: str | None = None) -> None:
        self.setProperty("state", state)
        if text is not None:
            self.label.setText(text)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if self._first_path_url(event.mimeData()) is not None:
            event.acceptProposedAction()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        path = self._first_path_url(event.mimeData())
        if path is not None:
            self.path_dropped.emit(path)
            event.acceptProposedAction()

    @staticmethod
    def _first_path_url(mime_data: QtCore.QMimeData) -> Path | None:
        for url in mime_data.urls():
            path = Path(url.toLocalFile())
            if path.is_dir() or path.suffix.lower() == ".dem":
                return path
        return None


class CommandCard(QtWidgets.QFrame):
    copy_requested = QtCore.Signal(str, str)

    def __init__(self, fallback_title: str) -> None:
        super().__init__()
        self.fallback_title = fallback_title
        self.setObjectName("card")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        self.title = QtWidgets.QLabel(fallback_title)
        self.title.setObjectName("cardTitle")
        self.indices = QtWidgets.QLineEdit()
        self.indices.setReadOnly(True)
        self.indices.setObjectName("slotField")
        self.command = QtWidgets.QLineEdit()
        self.command.setReadOnly(True)
        self.command.setObjectName("commandField")
        self.players = QtWidgets.QLabel("No players loaded yet.")
        self.players.setWordWrap(True)
        self.players.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        copy_button = QtWidgets.QPushButton("Copy command")
        copy_button.setObjectName("primaryButton")
        copy_button.clicked.connect(lambda: self.copy_requested.emit(self.title.text(), self.command.text()))

        layout.addWidget(self.title)
        layout.addWidget(QtWidgets.QLabel("Detected spec_player slots"))
        layout.addWidget(self.indices)
        layout.addWidget(QtWidgets.QLabel("Console command"))
        layout.addWidget(self.command)
        layout.addWidget(copy_button, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(QtWidgets.QLabel("Players"))
        layout.addWidget(self.players, stretch=1)

    def clear(self) -> None:
        self.title.setText(self.fallback_title)
        self.indices.clear()
        self.command.clear()
        self.players.setText("No players loaded yet.")


class ListenVoiceApp(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1120, 760)
        self.setMinimumSize(920, 640)

        self.demo_folder: Path | None = None
        self.demo_path: Path | None = None
        self.available_demos: list[Path] = []
        self.rows: list[tuple[str, dict[str, Any]]] = []
        self.auto_team_groups: list[tuple[str, list[int], list[str]]] = []
        self.spec_player_names: dict[int, str] = {}
        self.raw_commands: list[str] = []
        self.worker: ParserWorker | None = None
        self.settings = QtCore.QSettings(SETTINGS_ORG, SETTINGS_APP)
        self.theme_mode = self.settings.value(SETTINGS_THEME_MODE, "system", str)
        if self.theme_mode not in {"system", "light", "dark"}:
            self.theme_mode = "system"

        self._build_ui()
        self._apply_styles()
        self.apply_show_details_setting()
        self.restore_last_demo_folder()

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(12)

        title = QtWidgets.QLabel(APP_TITLE)
        title.setObjectName("title")
        subtitle = QtWidgets.QLabel("Generate ready-to-paste CS2 voice commands for FACEIT demos.")
        subtitle.setObjectName("muted")
        root.addWidget(title)
        root.addWidget(subtitle)

        self.drop_area = DropArea()
        self.drop_area.mousePressEvent = lambda _event: self.choose_demo_folder()  # type: ignore[method-assign]
        self.drop_area.path_dropped.connect(self.handle_dropped_path)
        root.addWidget(self.drop_area)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        root.addWidget(self.progress_bar)

        picker = QtWidgets.QHBoxLayout()
        self.folder_display = QtWidgets.QLineEdit()
        self.folder_display.setReadOnly(True)
        self.folder_display.setPlaceholderText("No demo folder selected")
        choose_folder_button = QtWidgets.QPushButton("Choose folder")
        choose_folder_button.setObjectName("primaryButton")
        choose_folder_button.clicked.connect(self.choose_demo_folder)
        refresh_button = QtWidgets.QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_demo_list)
        picker.addWidget(self.folder_display, stretch=1)
        picker.addWidget(choose_folder_button)
        picker.addWidget(refresh_button)
        root.addLayout(picker)

        self.demo_list = QtWidgets.QComboBox()
        self.demo_list.setPlaceholderText("Select a demo")
        self.demo_list.activated.connect(self.load_selected_demo)
        root.addWidget(self.demo_list)

        self.tabs = QtWidgets.QTabWidget()
        root.addWidget(self.tabs, stretch=1)

        self.main_tab = QtWidgets.QWidget()
        self.manual_tab = QtWidgets.QWidget()
        self.settings_tab = QtWidgets.QWidget()
        self.tabs.addTab(self.main_tab, "Commands")
        self.tabs.addTab(self.manual_tab, "Manual correction")
        self.tabs.addTab(self.settings_tab, "Settings")
        self._build_main_tab()
        self._build_manual_tab()
        self._build_settings_tab()

        self.status = QtWidgets.QLabel("Ready.")
        self.status.setObjectName("muted")
        root.addWidget(self.status)

    def _build_main_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.main_tab)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        cards = QtWidgets.QHBoxLayout()
        cards.setSpacing(12)
        self.team_a_card = CommandCard("Team A")
        self.team_b_card = CommandCard("Team B")
        self.team_a_card.copy_requested.connect(self.copy_command_text)
        self.team_b_card.copy_requested.connect(self.copy_command_text)
        cards.addWidget(self.team_a_card)
        cards.addWidget(self.team_b_card)
        layout.addLayout(cards)

        self.details_panel = QtWidgets.QWidget()
        details_layout = QtWidgets.QVBoxLayout(self.details_panel)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(12)

        table_header = QtWidgets.QHBoxLayout()
        table_title = QtWidgets.QLabel("Parsed demo details")
        table_title.setObjectName("sectionTitle")
        self.auto_fill_button = QtWidgets.QPushButton("Auto-fill teams")
        self.auto_fill_button.clicked.connect(lambda: self.auto_fill_teams(update_status=True))
        table_header.addWidget(table_title)
        table_header.addStretch()
        table_header.addWidget(self.auto_fill_button)
        details_layout.addLayout(table_header)

        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Spec #", "Name", "SteamID", "Team", "User ID", "Raw"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        details_layout.addWidget(self.table, stretch=1)
        layout.addWidget(self.details_panel, stretch=1)

    def _build_manual_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.manual_tab)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        self.manual_team_a = self._manual_row(layout, "Team A indices")
        self.manual_team_b = self._manual_row(layout, "Team B indices")
        self.manual_custom = self._manual_row(layout, "Custom indices")

        selected_buttons = QtWidgets.QHBoxLayout()
        selected_buttons.addWidget(self._button("Add selected to Team A", lambda: self.add_selected_to(self.manual_team_a)))
        selected_buttons.addWidget(self._button("Add selected to Team B", lambda: self.add_selected_to(self.manual_team_b)))
        selected_buttons.addWidget(self._button("Add selected to Custom", lambda: self.add_selected_to(self.manual_custom)))
        selected_buttons.addStretch()
        layout.addLayout(selected_buttons)

        action_buttons = QtWidgets.QHBoxLayout()
        action_buttons.addWidget(self._button("Generate", self.generate_commands, primary=True))
        action_buttons.addWidget(self._button("Copy all commands", self.copy_all_commands))
        action_buttons.addWidget(self._button("Clear manual fields", self.clear_manual_fields))
        action_buttons.addStretch()
        layout.addLayout(action_buttons)

        note = QtWidgets.QLabel("Manual entries accept comma/space-separated values and ranges, e.g. 1, 2, 5-7.")
        note.setObjectName("muted")
        layout.addWidget(note)
        layout.addStretch()

    def _build_settings_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.settings_tab)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        theme_row = QtWidgets.QHBoxLayout()
        theme_label = QtWidgets.QLabel("Theme")
        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItem("System", "system")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(self.theme_mode)))
        self.theme_combo.currentIndexChanged.connect(self.change_theme_mode)
        theme_row.addWidget(theme_label)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch()
        layout.addLayout(theme_row)

        self.show_details_checkbox = QtWidgets.QCheckBox("Show parsed demo details")
        self.show_details_checkbox.setChecked(self.show_parsed_details_enabled())
        self.show_details_checkbox.toggled.connect(self.change_show_details)
        layout.addWidget(self.show_details_checkbox)
        layout.addStretch()

    def _manual_row(self, parent: QtWidgets.QVBoxLayout, label_text: str) -> QtWidgets.QLineEdit:
        label = QtWidgets.QLabel(label_text)
        edit = QtWidgets.QLineEdit()
        parent.addWidget(label)
        parent.addWidget(edit)
        return edit

    def _button(self, text: str, callback: Any, primary: bool = False) -> QtWidgets.QPushButton:
        button = QtWidgets.QPushButton(text)
        if primary:
            button.setObjectName("primaryButton")
        button.clicked.connect(callback)
        return button

    def show_parsed_details_enabled(self) -> bool:
        value = self.settings.value(SETTINGS_SHOW_DETAILS, False)
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes", "on"}

    def apply_show_details_setting(self) -> None:
        if hasattr(self, "details_panel"):
            self.details_panel.setVisible(self.show_parsed_details_enabled())

    def change_show_details(self, checked: bool) -> None:
        self.settings.setValue(SETTINGS_SHOW_DETAILS, checked)
        self.apply_show_details_setting()

    def change_theme_mode(self, *_args: object) -> None:
        mode = self.theme_combo.currentData()
        self.theme_mode = str(mode) if mode in {"system", "light", "dark"} else "system"
        self.settings.setValue(SETTINGS_THEME_MODE, self.theme_mode)
        self._apply_styles()

    def _apply_styles(self) -> None:
        theme = current_theme(self.theme_mode)
        self.setStyleSheet(
            f"""
            QMainWindow {{
                background: {theme.bg};
                color: {theme.text};
            }}
            QWidget {{
                color: {theme.text};
                font-family: {UI_FONT_FAMILY}, {UI_FONT_FALLBACK};
                font-size: 10pt;
            }}
            QMainWindow > QWidget {{
                background: {theme.bg};
            }}
            QLabel {{
                background: transparent;
                color: {theme.text};
            }}
            QLabel#title {{
                font-size: 18pt;
                font-weight: 700;
            }}
            QLabel#sectionTitle, QLabel#cardTitle {{
                font-size: 12pt;
                font-weight: 700;
            }}
            QLabel#muted {{
                color: {theme.muted};
            }}
            QFrame#dropArea {{
                border-radius: 8px;
                min-height: 96px;
            }}
            QFrame#dropArea[state="idle"] {{
                background: {theme.drop_idle_bg};
                border: 2px solid {theme.drop_idle_border};
            }}
            QFrame#dropArea[state="parsing"] {{
                background: {theme.drop_parsing_bg};
                border: 2px solid {theme.drop_parsing_border};
            }}
            QFrame#dropArea[state="success"] {{
                background: {theme.drop_success_bg};
                border: 2px solid {theme.drop_success_border};
            }}
            QFrame#dropArea[state="error"] {{
                background: {theme.drop_error_bg};
                border: 2px solid {theme.drop_error_border};
            }}
            QLabel#dropIcon {{
                color: {theme.accent};
                font-weight: 700;
            }}
            QLabel#dropLabel {{
                font-size: 12pt;
                font-weight: 700;
            }}
            QFrame#card {{
                background: {theme.card};
                border: 1px solid {theme.border};
                border-radius: 8px;
            }}
            QLineEdit {{
                background: {theme.input_bg};
                border: 1px solid {theme.border};
                border-radius: 5px;
                color: {theme.text};
                padding: 6px;
            }}
            QLineEdit#commandField {{
                background: {theme.input_readonly};
                font-family: {MONO_FONT_FAMILY};
            }}
            QLineEdit#slotField {{
                background: {theme.input_readonly};
                font-family: {MONO_FONT_FAMILY};
            }}
            QComboBox {{
                background: {theme.input_bg};
                border: 1px solid {theme.border};
                border-radius: 5px;
                color: {theme.text};
                padding: 6px;
            }}
            QComboBox QAbstractItemView {{
                background: {theme.card};
                color: {theme.text};
                selection-background-color: {theme.selection};
                selection-color: {theme.text};
            }}
            QCheckBox {{
                background: transparent;
                color: {theme.text};
                spacing: 8px;
            }}
            QProgressBar {{
                background: {theme.input_bg};
                border: 1px solid {theme.border};
                border-radius: 4px;
                min-height: 8px;
                max-height: 8px;
            }}
            QProgressBar::chunk {{
                background: {theme.accent};
                border-radius: 4px;
            }}
            QPushButton {{
                background: {theme.card};
                border: 1px solid {theme.border};
                border-radius: 5px;
                color: {theme.text};
                padding: 7px 12px;
            }}
            QPushButton:hover {{
                border-color: {theme.accent};
            }}
            QPushButton#primaryButton {{
                background: {theme.accent};
                border-color: {theme.accent_dark};
                color: #ffffff;
            }}
            QPushButton#primaryButton:hover {{
                background: {theme.accent_dark};
            }}
            QTableWidget {{
                background: {theme.card};
                alternate-background-color: {theme.code_bg};
                border: 1px solid {theme.border};
                color: {theme.text};
                gridline-color: {theme.border};
                selection-background-color: {theme.selection};
                selection-color: {theme.text};
            }}
            QHeaderView::section {{
                background: {theme.header};
                border: 0;
                border-right: 1px solid {theme.border};
                color: {theme.text};
                padding: 6px;
                font-weight: 700;
            }}
            QTabWidget::pane {{
                border: 0;
            }}
            QTabBar::tab {{
                background: {theme.tab};
                border: 1px solid {theme.border};
                color: {theme.text};
                padding: 8px 14px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }}
            QTabBar::tab:selected {{
                background: {theme.card};
            }}
            QScrollBar:vertical, QScrollBar:horizontal {{
                background: {theme.bg};
            }}
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
                background: {theme.border};
                border-radius: 4px;
            }}
            """
        )

    def choose_demo_folder(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select FACEIT demo folder", "")
        if folder:
            self.load_demo_folder(Path(folder))

    def handle_dropped_path(self, path: Path) -> None:
        if path.is_dir():
            self.load_demo_folder(path)
        elif path.suffix.lower() == ".dem":
            self.load_demo_folder(path.parent, selected_demo=path)
        else:
            QtWidgets.QMessageBox.critical(self, APP_TITLE, "Drop a demo folder or a .dem file.")

    def load_demo_folder(self, folder: Path, selected_demo: Path | None = None) -> None:
        if not folder.exists() or not folder.is_dir():
            QtWidgets.QMessageBox.critical(self, APP_TITLE, "Select an existing folder.")
            return

        self.demo_folder = folder
        self.settings.setValue(SETTINGS_DEMO_FOLDER, str(folder))
        self.folder_display.setText(str(folder))
        self.refresh_demo_list()
        self.drop_area.set_state("idle", f"Loaded folder: {folder.name}")

        if selected_demo is not None:
            self.select_demo_in_list(selected_demo)
            self.load_demo(selected_demo)
        elif self.available_demos:
            self.status.setText(f"Found {len(self.available_demos)} demo file{'s' if len(self.available_demos) != 1 else ''}.")
        else:
            self.status.setText("No .dem files found in selected folder.")

    def restore_last_demo_folder(self) -> None:
        folder_text = self.settings.value(SETTINGS_DEMO_FOLDER, "", str)
        if not folder_text:
            return
        folder = Path(folder_text)
        if folder.exists() and folder.is_dir():
            self.load_demo_folder(folder)
        else:
            self.settings.remove(SETTINGS_DEMO_FOLDER)

    def refresh_demo_list(self) -> None:
        self.demo_list.blockSignals(True)
        self.demo_list.clear()
        self.available_demos = []

        if self.demo_folder is None:
            self.demo_list.addItem("Choose a folder first")
            self.demo_list.setEnabled(False)
            self.demo_list.blockSignals(False)
            return

        self.available_demos = sorted(
            self.demo_folder.glob("*.dem"),
            key=lambda path: (path.stat().st_mtime, path.name.lower()),
            reverse=True,
        )
        self.demo_list.setEnabled(bool(self.available_demos))
        if self.available_demos:
            for demo in self.available_demos:
                size_mb = demo.stat().st_size / (1024 * 1024)
                modified = QtCore.QDateTime.fromSecsSinceEpoch(int(demo.stat().st_mtime)).toString("yyyy-MM-dd HH:mm")
                self.demo_list.addItem(f"{demo.name}  ({size_mb:.1f} MB, {modified})", str(demo))
            self.demo_list.setCurrentIndex(-1)
        else:
            self.demo_list.addItem("No .dem files found")

        self.demo_list.blockSignals(False)

    def select_demo_in_list(self, demo: Path) -> None:
        for index in range(self.demo_list.count()):
            item_path = self.demo_list.itemData(index)
            if item_path and Path(item_path) == demo:
                self.demo_list.setCurrentIndex(index)
                return

    def load_selected_demo(self, index: int) -> None:
        item_path = self.demo_list.itemData(index)
        if item_path:
            self.load_demo(Path(item_path))

    def load_demo(self, path: Path) -> None:
        if not path.exists():
            QtWidgets.QMessageBox.critical(self, APP_TITLE, "Select an existing .dem file first.")
            return
        if path.suffix.lower() != ".dem":
            QtWidgets.QMessageBox.critical(self, APP_TITLE, "Select a .dem file.")
            return
        if self.worker is not None and self.worker.isRunning():
            self.status.setText("Already parsing a demo.")
            return

        self.demo_path = path
        self.clear_results()
        self.drop_area.set_state("parsing", f"Parsing {path.name}...")
        self.progress_bar.show()
        self.status.setText("Parsing demo...")
        self.worker = ParserWorker(path)
        self.worker.completed.connect(self._show_inspection)
        self.worker.failed.connect(self._show_parse_error)
        self.worker.finished.connect(lambda: setattr(self, "worker", None))
        self.worker.start()

    def _show_inspection(self, rows: object, notes: object, _slot_start: int, path: object) -> None:
        self.rows = list(rows)  # type: ignore[arg-type]
        self.auto_team_groups = build_auto_team_groups(self.rows)
        self._set_table_rows(self.rows)
        parsed = self.auto_fill_teams(update_status=False)
        self.generate_commands()

        path_obj = Path(path)  # type: ignore[arg-type]
        self.progress_bar.hide()
        self.drop_area.set_state("success", f"Loaded: {path_obj.name}")
        note_text = " ".join(list(notes)[-1:]) if notes else ""  # type: ignore[arg-type]
        if parsed:
            self.status.setText(f"Parsed {len(self.rows)} players and generated commands. {note_text}".strip())
        else:
            self.status.setText(f"Parsed {len(self.rows)} rows, but could not auto-detect two teams. {note_text}".strip())

    def _show_parse_error(self, message: str, missing_parser: bool) -> None:
        self.progress_bar.hide()
        self.drop_area.set_state("error", "Demo parsing failed")
        title = "cs-demo-analyzer missing" if missing_parser else "Demo parsing failed"
        dialog = QtWidgets.QMessageBox(self)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Critical)
        dialog.setWindowTitle(APP_TITLE)
        dialog.setText(title)
        if missing_parser:
            dialog.setInformativeText("Configure csda.exe, then try again.")
        else:
            dialog.setInformativeText("This file could not be parsed as a FACEIT CS2 demo.")
        dialog.setDetailedText(message)
        dialog.exec()
        self.status.setText(title + ".")

    def _set_table_rows(self, rows: list[tuple[str, dict[str, Any]]]) -> None:
        self.table.setRowCount(0)
        self.spec_player_names = {}
        for source, row in rows:
            if source != "player_info":
                continue
            spec = int(row.get("spec_index", 0))
            name = compact_value(row.get("name") or "")
            if spec and name:
                self.spec_player_names[spec] = name

            table_row = self.table.rowCount()
            self.table.insertRow(table_row)
            values = [
                str(spec),
                name,
                compact_value(row.get("steamid") or ""),
                compact_value(row.get("team") or ""),
                compact_value(row.get("user_id") or ""),
                json.dumps(row, default=str),
            ]
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, spec)
                self.table.setItem(table_row, column, item)

    def auto_fill_teams(self, update_status: bool = True) -> bool:
        if len(self.auto_team_groups) < 2:
            if update_status:
                self.status.setText("Need two detected teams before auto-fill can work.")
            return False

        first_team, first_indices, first_players = self.auto_team_groups[0]
        second_team, second_indices, second_players = self.auto_team_groups[1]
        self.team_a_card.title.setText(f"Team A ({first_team})")
        self.team_b_card.title.setText(f"Team B ({second_team})")
        self.team_a_card.indices.setText(", ".join(map(str, first_indices)))
        self.team_b_card.indices.setText(", ".join(map(str, second_indices)))
        self.manual_team_a.setText(", ".join(map(str, first_indices)))
        self.manual_team_b.setText(", ".join(map(str, second_indices)))
        self.team_a_card.players.setText(self._format_player_list(first_indices, first_players))
        self.team_b_card.players.setText(self._format_player_list(second_indices, second_players))
        if update_status:
            self.generate_commands()
            self.status.setText(
                f"Auto-filled Team A={first_team} ({', '.join(map(str, first_indices))}); "
                f"Team B={second_team} ({', '.join(map(str, second_indices))})."
            )
        return True

    @staticmethod
    def _format_player_list(indices: list[int], names: list[str]) -> str:
        if not indices:
            return "No players loaded yet."
        lines: list[str] = []
        for position, index in enumerate(indices):
            name = names[position] if position < len(names) and names[position] else f"Player {index}"
            lines.append(f"{index}. {name}")
        return "\n".join(lines)

    def refresh_team_player_lists(self) -> None:
        try:
            team_a = parse_index_text(self.team_a_card.indices.text())
            team_b = parse_index_text(self.team_b_card.indices.text())
        except ValueError:
            return
        self.team_a_card.players.setText(
            self._format_player_list(team_a, [self.spec_player_names.get(index, f"Player {index}") for index in team_a])
        )
        self.team_b_card.players.setText(
            self._format_player_list(team_b, [self.spec_player_names.get(index, f"Player {index}") for index in team_b])
        )

    def generate_commands(self) -> None:
        self.team_a_card.indices.setText(self.manual_team_a.text())
        self.team_b_card.indices.setText(self.manual_team_b.text())
        sections = [
            ("Team A", self.team_a_card.indices.text(), self.team_a_card),
            ("Team B", self.team_b_card.indices.text(), self.team_b_card),
            ("Custom", self.manual_custom.text(), None),
        ]
        raw_commands: list[str] = []
        self.team_a_card.command.clear()
        self.team_b_card.command.clear()
        try:
            for title, text, card in sections:
                indices = parse_index_text(text)
                if not indices:
                    continue
                raw_command = command_for_indices(indices)
                raw_commands.append(raw_command)
                if card is not None:
                    card.command.setText(raw_command)
                elif title == "Custom":
                    QtWidgets.QApplication.clipboard().setText(raw_command)
                    self.status.setText("Generated and copied custom command.")
        except ValueError as exc:
            QtWidgets.QMessageBox.critical(self, APP_TITLE, str(exc))
            return

        self.raw_commands = raw_commands
        self.refresh_team_player_lists()
        if raw_commands:
            self.status.setText("Commands generated.")
        else:
            self.status.setText("Enter at least one index.")

    def selected_indices(self) -> list[int]:
        indices: set[int] = set()
        for item in self.table.selectedItems():
            value = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(value, int) and value > 0:
                indices.add(value)
        return sorted(indices)

    def add_selected_to(self, edit: QtWidgets.QLineEdit) -> None:
        selected = self.selected_indices()
        if not selected:
            self.status.setText("Select one or more rows in Parsed demo details first.")
            return
        try:
            existing = parse_index_text(edit.text())
        except ValueError as exc:
            QtWidgets.QMessageBox.critical(self, APP_TITLE, f"Existing index field contains invalid text:\n{exc}")
            return
        edit.setText(", ".join(map(str, sorted(set(existing + selected)))))
        self.status.setText(f"Added indices: {', '.join(map(str, selected))}.")

    def copy_command_text(self, title: str, command: str) -> None:
        command = command.strip()
        if not command:
            self.generate_commands()
            command = self.team_a_card.command.text() if title.startswith("Team A") else self.team_b_card.command.text()
        if not command:
            self.status.setText(f"{title} has no command to copy.")
            return
        QtWidgets.QApplication.clipboard().setText(command)
        self.status.setText(f"Copied {title} command.")

    def copy_all_commands(self) -> None:
        if not self.raw_commands:
            self.generate_commands()
        if not self.raw_commands:
            self.status.setText("Nothing to copy.")
            return
        QtWidgets.QApplication.clipboard().setText("\n".join(self.raw_commands))
        self.status.setText(f"Copied {len(self.raw_commands)} command{'s' if len(self.raw_commands) != 1 else ''}.")

    def clear_manual_fields(self) -> None:
        self.manual_team_a.clear()
        self.manual_team_b.clear()
        self.manual_custom.clear()
        self.team_a_card.command.clear()
        self.team_b_card.command.clear()
        self.raw_commands = []
        self.status.setText("Manual fields cleared.")

    def clear_results(self) -> None:
        self.rows = []
        self.auto_team_groups = []
        self.spec_player_names = {}
        self.raw_commands = []
        self.team_a_card.clear()
        self.team_b_card.clear()
        self.manual_team_a.clear()
        self.manual_team_b.clear()
        self.manual_custom.clear()
        self.table.setRowCount(0)


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    app.setFont(QtGui.QFont(UI_FONT_FAMILY, 10))
    window = ListenVoiceApp()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
