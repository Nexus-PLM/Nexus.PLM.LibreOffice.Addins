"""There is no Release command, and nothing may quietly put one back.

Marc's decision, Sep 26 2026: a revision reaches Released only by running a workflow. The command
posted to ``/plm/release``, which writes the lifecycle status straight onto the revision through the
service's generic attribute write, so it went around every approval the workflow declares. Neither
the web client nor the WPF client has ever offered it, so the add-ins were the odd ones out.

This is a removal, and a removal with no test is a removal that comes back by accident. So these
hold every surface that used to carry it: the script module, the client, the toolbar registration
and the stacked menu. They also hold that the replacement is still reachable, because removing the
command without leaving a way to release would be a different and worse change.

    python -m unittest discover -s tests/python
"""

import io
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "extension", "python", "pythonpath"))

from nexusplm import client as client_module


def _read(*parts):
    with io.open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


class NoReleaseCommand(unittest.TestCase):

    def test_the_client_cannot_call_the_release_endpoint(self):
        # The client is the only place an endpoint string lives, so this is the one assertion that
        # holds whatever else is added later.
        self.assertFalse(hasattr(client_module.Client, "release"))
        self.assertNotIn("/plm/release", _read("extension", "python", "pythonpath", "nexusplm", "client.py"))

    def test_the_script_module_neither_defines_nor_exports_it(self):
        source = _read("extension", "python", "nexus_commands.py")
        self.assertNotIn("def release(", source)
        self.assertNotIn('@_command("Release")', source)

    def test_no_toolbar_button_or_menu_entry_points_at_it(self):
        addons = _read("extension", "Addons.xcu")
        self.assertNotIn("nexus_commands.py$release", addons)
        self.assertNotIn("Release_16.png", addons)
        self.assertNotIn("Release_26.png", addons)

    def test_no_stacked_menu_entry_offers_it(self):
        source = _read("extension", "python", "nexusplm_controllers.py")
        self.assertNotIn('"release"', source)

    def test_the_way_to_release_is_still_on_the_toolbar(self):
        # Removing the command without leaving a way to release would strand every document.
        self.assertIn("nexus_commands.py$new_workflow", _read("extension", "Addons.xcu"))
        self.assertIn("new_workflow", _read("extension", "python", "nexus_commands.py"))


if __name__ == "__main__":
    unittest.main()
