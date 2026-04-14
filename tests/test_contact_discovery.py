import tempfile
import unittest
from pathlib import Path

from app.contact_discovery import discover_contacts
from app.memory import SQLiteMemory


class FakeADB(object):
    def shell(self, command, check=True, timeout=None):
        return "Row: 0 display_name=Dave Zhu, data1=+18059577464\n"


class ContactDiscoveryTests(unittest.TestCase):
    def test_discover_contacts_persists_memory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = SQLiteMemory(db_path=str(Path(temp_dir) / "memory.db"))
            contacts = discover_contacts(FakeADB(), memory)

            self.assertEqual(contacts[0]["contact_name"], "Dave Zhu")
            remembered = memory.get_best_contact()
            self.assertEqual(remembered["phone_number"], "+18059577464")


if __name__ == "__main__":
    unittest.main()
