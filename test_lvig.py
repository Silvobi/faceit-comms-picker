"""Run with: py -m unittest -v test_lvig"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6 import QtCore, QtGui, QtTest, QtWidgets

import lvig


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        if os.name == "nt":
            for font in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf"):
                QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + font)
        cls.app.setFont(QtGui.QFont(lvig.UI_FONT_FAMILY, 10))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        settings = QtCore.QSettings(str(self.folder / "settings.ini"), QtCore.QSettings.Format.IniFormat)
        with patch.object(lvig.QtCore, "QSettings", return_value=settings):
            self.window = lvig.ListenVoiceApp()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def set_slots(self, *values):
        for spin, value in zip(self.window.raw_slots, values):
            spin.setValue(value)

    def test_raw_conversion_empty_duplicates_and_signed_boundary(self):
        self.assertEqual(len(self.window.raw_slots), 5)
        self.window.generate_raw_command()
        self.assertEqual(self.window.raw_command.text(), "")
        self.assertFalse(self.window.raw_copy_button.isEnabled())
        self.set_slots(1, 4, 5, 7, 8)
        self.window.generate_raw_command()
        self.assertEqual(self.window.raw_command.text(), "tv_listen_voice_indices 217")
        self.window.clear_raw_fields()
        self.set_slots(32, 32)
        self.window.copy_raw_command()
        self.assertEqual(self.app.clipboard().text(), "tv_listen_voice_indices -2147483648")
        self.window.raw_slots[1].setValue(1)
        self.assertEqual(self.window.raw_command.text(), "")
        self.assertFalse(self.window.raw_copy_button.isEnabled())
        self.window.generate_raw_command()
        self.assertEqual(self.window.raw_command.text(), "tv_listen_voice_indices -2147483647")

    def test_edit_and_mouse_wheel_change_slots_and_invalidate_result(self):
        self.window.tabs.setCurrentWidget(self.window.raw_tab)
        self.app.processEvents()
        spin = self.window.raw_slots[0]
        spin.setValue(4)
        self.window.generate_raw_command()
        spin.setFocus()
        point = QtCore.QPointF(spin.rect().center())
        event = QtGui.QWheelEvent(
            point, QtCore.QPointF(spin.mapToGlobal(spin.rect().center())),
            QtCore.QPoint(), QtCore.QPoint(0, 120), QtCore.Qt.MouseButton.NoButton,
            QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.ScrollPhase.NoScrollPhase, False,
        )
        self.app.sendEvent(spin, event)
        self.assertEqual(spin.value(), 5)
        self.assertFalse(self.window.raw_copy_button.isEnabled())
        self.window.generate_raw_command()
        spin.lineEdit().selectAll()
        QtTest.QTest.keyClicks(spin.lineEdit(), "12")
        self.assertEqual(self.window.raw_command.text(), "")
        self.window.generate_raw_command()
        self.assertEqual(self.window.raw_command.text(), "tv_listen_voice_indices 2048")

    def test_demo_click_and_folder_button_open_different_dialogs(self):
        demo = self.folder / "match.dem"
        demo.touch()
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value=(str(demo), "")) as file_dialog, \
             patch.object(self.window, "load_demo") as load:
            QtTest.QTest.mouseClick(self.window.drop_area, QtCore.Qt.MouseButton.LeftButton)
            file_dialog.assert_called_once()
            load.assert_called_once_with(demo)
            self.assertEqual(self.window.demo_folder, self.folder)
        with patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value=str(self.folder)) as folder_dialog, \
             patch.object(self.window, "load_demo") as load:
            button = next(button for button in self.window.findChildren(QtWidgets.QPushButton)
                          if button.text() == "Choose folder")
            button.click()
            folder_dialog.assert_called_once()
            load.assert_not_called()
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value=("", "")), \
             patch.object(self.window, "load_demo_folder") as load_folder:
            self.window.choose_demo_file()
            load_folder.assert_not_called()

    def test_dropped_demo_and_folder_preserve_selection_behavior(self):
        demo = self.folder / "match.dem"
        demo.touch()
        with patch.object(self.window, "load_demo") as load:
            self.window.handle_dropped_path(demo)
            load.assert_called_once_with(demo)
            self.assertEqual(Path(self.window.demo_list.currentData()), demo)
        with patch.object(self.window, "load_demo") as load:
            self.window.handle_dropped_path(self.folder)
            load.assert_not_called()
        mime = QtCore.QMimeData()
        mime.setUrls([QtCore.QUrl.fromLocalFile(str(demo))])
        self.assertEqual(lvig.DropArea._first_path_url(mime), demo)

    def test_demo_results_and_raw_converter_are_independent(self):
        self.set_slots(1, 4, 5, 7, 8)
        self.window.generate_raw_command()
        rows = [("player_info", {"spec_index": index, "name": f"Player {index}", "team": team})
                for team, indices in (("CT", [3, 4, 5, 7, 9]), ("TERRORIST", [6, 8, 10, 11, 12]))
                for index in indices]
        self.window._show_inspection(rows, [], 3, self.folder / "match.dem")
        self.assertEqual(self.window.team_a_card.command.text(), "tv_listen_voice_indices 348")
        self.assertEqual(self.window.team_b_card.command.text(), "tv_listen_voice_indices 3744")
        self.assertEqual(self.window.raw_command.text(), "tv_listen_voice_indices 217")
        self.window.clear_raw_fields()
        self.assertEqual(self.window.team_a_card.command.text(), "tv_listen_voice_indices 348")
        self.window.clear_results()
        self.assertEqual(self.window.team_a_card.command.text(), "")

    def test_tabs_fill_window_at_multiple_sizes(self):
        for width in (920, 1120, 1440):
            self.window.resize(width, 900)
            self.app.processEvents()
            tabs = self.window.tabs
            bar = tabs.tabBar()
            self.assertEqual(bar.width(), tabs.contentsRect().width())
            widths = [bar.tabRect(index).width() for index in range(bar.count())]
            self.assertLessEqual(max(widths) - min(widths), 1)
            self.assertLessEqual(abs(bar.tabRect(3).right() + 1 - bar.width()), 1)

    def test_small_window_keeps_raw_result_visible_and_instructions_scrollable(self):
        self.window.resize(920, 640)
        self.window.tabs.setCurrentWidget(self.window.raw_tab)
        self.app.processEvents()
        self.set_slots(1, 4, 5, 7, 8)
        self.window.generate_raw_command()
        viewport = self.window.raw_scroll.viewport()
        bottom = self.window.raw_copy_button.mapTo(viewport, self.window.raw_copy_button.rect().bottomRight())
        self.assertTrue(viewport.rect().contains(bottom))
        scrollbar = self.window.raw_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        content = self.window.raw_scroll.widget()
        bottom = content.mapTo(viewport, content.rect().bottomLeft())
        self.assertLessEqual(bottom.y(), viewport.height())


if __name__ == "__main__":
    unittest.main()
