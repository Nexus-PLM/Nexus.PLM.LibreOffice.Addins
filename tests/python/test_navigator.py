"""The navigator's tree shape, tested without an office or a server.

The folder list is exactly what ``GET /plm/navigation/folders`` answers on the live server —
system folders nested under "Recently Modified", a user folder at the top, counts and all.
"""

import unittest

from nexusplm import navigator


def _folder(folder_id, name, parent=None, order=0, count=0, system=False):
    return {
        "folder_id": folder_id, "name": name, "parent_id": parent,
        "sort_order": order, "object_count": count, "is_system": system,
    }


LIVE_SHAPE = [
    _folder("ee71f8bf", "Beans & Bang", None, 0, 2),
    _folder("sys-by-me", "By Me", "sys-recently-modified", 0, 21, True),
    _folder("sys-my-working", "My Working", None, 0, 10, True),
    _folder("sys-by-my-group", "By My Group", "sys-recently-modified", 1, 21, True),
    _folder("sys-recently-modified", "Recently Modified", None, 1, 0, True),
    _folder("sys-by-my-project", "By My Project", "sys-recently-modified", 2, 7, True),
]


class TreeFrom(unittest.TestCase):
    def test_a_parentless_folder_is_a_root(self):
        roots = navigator.tree_from(LIVE_SHAPE)

        self.assertEqual(
            ["Beans & Bang (2)", "My Working (10)", "Recently Modified"],
            [node["label"] for node in roots])

    def test_children_hang_off_their_parent_in_sort_order(self):
        roots = navigator.tree_from(LIVE_SHAPE)
        recently = [n for n in roots if n["folder"]["folder_id"] == "sys-recently-modified"][0]

        self.assertEqual(
            ["By Me (21)", "By My Group (21)", "By My Project (7)"],
            [child["label"] for child in recently["children"]])

    def test_a_folder_whose_parent_is_missing_becomes_a_root(self):
        # Better a branch in the wrong place than a folder the user cannot reach at all.
        orphan = _folder("orphan", "Orphan", "a-folder-not-in-the-list")

        roots = navigator.tree_from([orphan])

        self.assertEqual(["Orphan"], [node["label"] for node in roots])

    def test_a_folder_that_claims_to_be_its_own_parent_is_a_root(self):
        loop = _folder("self", "Loop", "self")

        roots = navigator.tree_from([loop])

        self.assertEqual(["Loop"], [node["label"] for node in roots])
        self.assertEqual([], roots[0]["children"])

    def test_a_folder_with_no_id_is_not_a_folder(self):
        roots = navigator.tree_from([{"name": "No id"}, _folder("real", "Real")])

        self.assertEqual(["Real"], [node["label"] for node in roots])

    def test_nothing_at_all_is_no_tree_rather_than_an_error(self):
        self.assertEqual([], navigator.tree_from(None))
        self.assertEqual([], navigator.tree_from([]))

    def test_an_empty_folder_shows_no_count(self):
        roots = navigator.tree_from([_folder("f", "Empty", count=0)])

        self.assertEqual("Empty", roots[0]["label"])

    def test_a_folder_with_no_name_still_has_a_line(self):
        roots = navigator.tree_from([_folder("f", "   ")])

        self.assertEqual("(unnamed)", roots[0]["label"])


class Flatten(unittest.TestCase):
    def test_depth_is_how_far_a_node_is_from_the_top(self):
        flat = navigator.flatten(navigator.tree_from(LIVE_SHAPE))

        self.assertEqual(
            [(0, "Beans & Bang (2)"), (0, "My Working (10)"), (0, "Recently Modified"),
             (1, "By Me (21)"), (1, "By My Group (21)"), (1, "By My Project (7)")],
            [(depth, node["label"]) for depth, node in flat])


class ItemLabel(unittest.TestCase):
    def test_an_item_shows_its_part_number_and_revision(self):
        self.assertEqual(
            "LTD-00000009-ODT  A.003",
            navigator.item_label({"part_number": "LTD-00000009-ODT", "revision": "A.003"}))

    def test_an_item_with_no_revision_is_just_its_part_number(self):
        self.assertEqual(
            "LTD-00000009-ODT",
            navigator.item_label({"part_number": "LTD-00000009-ODT", "revision": ""}))

    def test_an_item_with_no_part_number_says_so(self):
        self.assertEqual("(no part number)", navigator.item_label({}))


if __name__ == "__main__":
    unittest.main()
