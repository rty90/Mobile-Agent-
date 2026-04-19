import unittest
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from app.desktop_ui import (
    build_run_kwargs,
    format_history_label,
    get_device_status_report,
    get_environment_status_report,
    load_recent_tasks,
    open_path_in_shell,
    save_recent_task,
)


class DesktopUiTests(unittest.TestCase):
    def test_build_run_kwargs_normalizes_blank_fields(self):
        payload = build_run_kwargs(
            task_text=" open keep and create a note ",
            device_id="",
            task_type="",
            planner_backend="rule",
            reasoner_backend="stack",
            agent_mode="",
            max_steps="4",
            dry_run=True,
            auto_confirm=False,
        )

        self.assertEqual(payload["task_text"], "open keep and create a note")
        self.assertIsNone(payload["device_id"])
        self.assertIsNone(payload["task_type_override"])
        self.assertIsNone(payload["agent_mode"])
        self.assertEqual(payload["max_steps"], 4)
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["auto_confirm"])

    def test_build_run_kwargs_rejects_empty_task(self):
        with self.assertRaises(ValueError):
            build_run_kwargs(task_text="   ")

    @patch("app.desktop_ui.ADBClient")
    @patch("app.desktop_ui.find_adb_path", return_value="C:\\adb\\adb.exe")
    def test_get_device_status_report_marks_ready_device(self, _find_adb_path, mock_adb_client):
        adb_instance = Mock()
        adb_instance.list_devices.return_value = [
            {"device_id": "emulator-5554", "status": "device"},
            {"device_id": "offline-1", "status": "offline"},
        ]
        mock_adb_client.return_value = adb_instance

        report = get_device_status_report("")

        self.assertTrue(report["ok"])
        self.assertTrue(report["connected"])
        self.assertEqual(report["adb_path"], "C:\\adb\\adb.exe")
        self.assertEqual(len(report["devices"]), 2)

    @patch("app.desktop_ui.find_adb_path", side_effect=RuntimeError("adb missing"))
    def test_get_device_status_report_surfaces_adb_lookup_failure(self, _find_adb_path):
        report = get_device_status_report("emulator-5554")

        self.assertFalse(report["ok"])
        self.assertFalse(report["connected"])
        self.assertEqual(report["requested_device"], "emulator-5554")
        self.assertIn("adb missing", report["message"])

    def test_open_path_in_shell_returns_false_for_missing_path(self):
        self.assertFalse(open_path_in_shell("Z:\\definitely-missing-path"))

    @patch("app.desktop_ui.os.path.exists", return_value=True)
    @patch("app.desktop_ui.os.startfile", create=True)
    def test_open_path_in_shell_uses_startfile_when_available(self, mock_startfile, _exists):
        self.assertTrue(open_path_in_shell("C:\\logs"))
        mock_startfile.assert_called_once()

    @patch("app.desktop_ui.os.path.exists", return_value=True)
    @patch("app.desktop_ui.os.startfile", side_effect=OSError("boom"), create=True)
    def test_open_path_in_shell_returns_false_when_shell_open_fails(self, _startfile, _exists):
        self.assertFalse(open_path_in_shell("C:\\logs"))

    @patch.dict(
        "app.desktop_ui.os.environ",
        {
            "DASHSCOPE_API_KEY": "secret",
            "LOCAL_TEXT_REASONER_BASE_URL": "http://127.0.0.1:9000/v1",
            "LOCAL_TEXT_REASONER_MODEL": "Qwen/Qwen3.5-0.8B",
            "REASONING_ENABLE_LOCAL_VL": "0",
            "REASONING_DISABLE_LOCAL_TEXT_AFTER_FAILURE": "1",
            "REASONING_REQUEST_TIMEOUT_SECONDS": "30",
        },
        clear=True,
    )
    def test_get_environment_status_report_reads_expected_fields(self):
        report = get_environment_status_report()

        self.assertTrue(report["cloud_api_configured"])
        self.assertTrue(report["local_text_configured"])
        self.assertFalse(report["local_vl_enabled"])
        self.assertTrue(report["disable_local_text_after_failure"])
        self.assertEqual(report["timeout_seconds"], "30")
        self.assertEqual(report["local_text_model"], "Qwen/Qwen3.5-0.8B")

    def test_recent_task_history_roundtrip_and_dedup(self):
        with TemporaryDirectory() as temp_dir:
            history_path = "{0}\\desktop_ui_history.json".format(temp_dir)
            save_recent_task(
                task_text="open keep and create a note",
                device_id="emulator-5554",
                task_type="guided_ui_task",
                reasoner_backend="stack",
                agent_mode="interactive",
                history_path=history_path,
                limit=3,
            )
            save_recent_task(
                task_text="open settings and inspect the current page",
                history_path=history_path,
                limit=3,
            )
            save_recent_task(
                task_text="open keep and create a note",
                device_id="emulator-5556",
                task_type="guided_ui_task",
                reasoner_backend="local",
                agent_mode="interactive",
                history_path=history_path,
                limit=3,
            )

            items = load_recent_tasks(history_path=history_path, limit=3)

            self.assertEqual(len(items), 2)
            self.assertEqual(items[0]["task_text"], "open keep and create a note")
            self.assertEqual(items[0]["device_id"], "emulator-5556")
            self.assertEqual(items[1]["task_text"], "open settings and inspect the current page")

    def test_format_history_label_includes_task_and_metadata(self):
        label = format_history_label(
            {
                "task_text": "open keep and create a note",
                "reasoner_backend": "stack",
                "updated_at": "2026-04-18 19:00:00",
            }
        )

        self.assertIn("open keep and create a note", label)
        self.assertIn("stack", label)
        self.assertIn("2026-04-18 19:00:00", label)


if __name__ == "__main__":
    unittest.main()
