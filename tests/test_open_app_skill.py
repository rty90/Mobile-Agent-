import unittest

from app.skills.open_app import OpenAppSkill


class DummyADB(object):
    def __init__(self):
        self.calls = []

    def is_package_installed(self, package_name):
        return True

    def open_app(self, package_name, activity_name=None):
        self.calls.append((package_name, activity_name))


class DummyState(object):
    def __init__(self):
        self.current_app = None


class DummyContext(object):
    def __init__(self):
        self.adb = DummyADB()
        self.state = DummyState()


class OpenAppSkillTests(unittest.TestCase):
    def test_accepts_app_name_alias(self):
        skill = OpenAppSkill()
        context = DummyContext()

        result = skill.execute({"app_name": "Messages"}, context)

        self.assertTrue(result["success"])
        self.assertEqual(context.adb.calls[0][0], "com.google.android.apps.messaging")

    def test_accepts_app_alias_field(self):
        skill = OpenAppSkill()
        context = DummyContext()

        result = skill.execute({"app": "Calendar"}, context)

        self.assertTrue(result["success"])
        self.assertEqual(context.adb.calls[0][0], "com.google.android.calendar")


if __name__ == "__main__":
    unittest.main()
