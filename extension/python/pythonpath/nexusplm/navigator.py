"""The shape of the navigator's folder tree, decided without LibreOffice anywhere near it.

``GET /plm/navigation/folders`` answers one flat list, every folder carrying its own
``parent_id``. A tree control wants the opposite — roots, each with its children — so the
nesting is worked out here, where it can be tested without an office running.

The endpoint is the Word Navigation pane's (``FolderBrowserServicesAdapter``), so the pane,
Word's pane and the Open dialog cannot disagree about what a folder contains.
"""


#: Shown after a folder's name when it holds anything, the way the Word pane shows it.
def _label(folder):
    """A folder's line in the tree: its name, and how much is in it."""
    name = (folder.get("name") or "").strip() or "(unnamed)"
    count = folder.get("object_count") or 0
    return "%s (%d)" % (name, count) if count else name


def _order(folder):
    """Folders sort the way the server asked, then by name so the order is never arbitrary."""
    return (folder.get("sort_order") or 0, (folder.get("name") or "").lower())


def tree_from(folders):
    """The folder list as roots with nested children.

    Each node is ``{"id", "label", "folder", "children"}``. A folder whose ``parent_id`` names
    a folder that is not in the list is treated as a root rather than dropped — a tree that
    silently loses folders is worse than one that shows a branch in the wrong place, and the
    server does filter its answer by what the user may read.
    """
    folders = [f for f in (folders or []) if f.get("folder_id")]
    nodes = {
        f["folder_id"]: {"id": f["folder_id"], "label": _label(f), "folder": f, "children": []}
        for f in folders
    }

    roots = []
    for folder in sorted(folders, key=_order):
        node = nodes[folder["folder_id"]]
        parent = nodes.get(folder.get("parent_id"))
        # A folder cannot be its own parent, and a parent outside the list is no parent at all.
        if parent is not None and parent is not node:
            parent["children"].append(node)
        else:
            roots.append(node)
    return roots


def flatten(roots):
    """Every node in display order, each with its depth — what a flat list control would draw.

    Useful for tests and for any host that has no real tree to give us.
    """
    out = []

    def walk(nodes, depth):
        for node in nodes:
            out.append((depth, node))
            walk(node["children"], depth + 1)

    walk(roots, 0)
    return out


def item_label(item):
    """One item's line under its folder: the part number, and its revision when it has one."""
    part = (item.get("part_number") or "").strip() or "(no part number)"
    revision = (item.get("revision") or "").strip()
    return "%s  %s" % (part, revision) if revision else part
