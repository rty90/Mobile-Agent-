import unittest

from app.demo_config import build_demo_message_config
from app.skills.read_screen import detect_page_name


class ReadScreenTests(unittest.TestCase):
    def test_detect_page_name_prefers_calendar_saved_page_over_generic_search(self):
        config = build_demo_message_config()
        visible_text = [
            "com.google.android.calendar:id/drawer_layout",
            "Search",
            "Jump to Today",
            "Open Tasks",
            "Creation menu",
            "Wednesday 15 April 2026, Open Schedule View",
        ]

        page = detect_page_name(visible_text, "", config)

        self.assertEqual(page, "reminder_saved")


if __name__ == "__main__":
    unittest.main()
