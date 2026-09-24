"""The Nexus PLM sidebar deck - a real docked panel, built from UNO controls.

LibreOffice asks a *UI element factory* for a panel whose ImplementationURL names it
(Factories.xcu), and the factory answers with a *UI element* whose real interface is a window
(Sidebar.xcu). This file is both halves.

Why controls and not a browser: LibreOffice draws its whole UI itself inside one top-level window.
Measured on 26.2 - the frame window hands back a Win32 handle, but the component window and any
child created through the toolkit expose no system-dependent interface at all, and
``EnumChildWindows`` on the frame returns **zero** children. A panel is a painted rectangle, not a
window, so there is nothing for a native control to be parented onto; and the frame does not set
``WS_CLIPCHILDREN``, so anything parented to *it* would be painted over on every repaint. The panel
is therefore drawn with the toolkit's own controls, which is also the only version that works
anywhere but Windows.

The panel shows what PLM knows about the document in front of you and offers the commands that
document's state allows. Every one of those decisions is in ``nexusplm.panel``, tested without an
office; what is here is the plumbing that cannot be.
"""

import os
import traceback

import uno
import unohelper
from com.sun.star.awt import (XActionListener, XMouseListener, XWindowListener,
                              Rectangle, Size)
from com.sun.star.awt.tree import XTreeExpansionListener
from com.sun.star.util import MeasureUnit
from com.sun.star.lang import XServiceInfo
from com.sun.star.ui import XUIElement, XUIElementFactory
from com.sun.star.ui.UIElementType import TOOLPANEL

from nexusplm import navigator as navigator_rules
from nexusplm import panel as panel_rules
from nexusplm.client import Client

FACTORY_IMPLEMENTATION = "com.nexusplm.libreoffice.PanelFactory"
FACTORY_SERVICE = "com.sun.star.ui.UIElementFactory"

SCRIPT = ("vnd.sun.star.script:NexusPLM.oxt|python|nexus_commands.py$%s"
          "?language=Python&location=user:uno_packages")

# Layout in appfont units, converted to pixels against the real window before anything is placed.
# setPosSize takes PIXELS, so using these numbers directly drew the whole panel about a fifth of
# its proper size with every row on top of the one above it — measured, on a 4K display.
_MARGIN = 4
_ROW_H = 10
_GAP = 2
_LABEL_W = 40
_BUTTON_H = 14
#: The navigator tree's heading, and the least height worth giving the tree itself.
_TREE_MIN_H = 60

# com.sun.star.awt.PosSize.POSSIZE - move and resize in one call.
_POSSIZE = 15


#: The same file every other half of this add-in writes to, so one document's story is in one place.
_LOG = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                    "NexusPLM", "Logs", "plmlibreofficeaddin.log")


def _log(message):
    """The panel's own line in the add-in log, so a failure in here is not silent.

    Best effort, as everywhere else here: the panel must not fail to draw because a log file
    could not be written.
    """
    try:
        os.makedirs(os.path.dirname(_LOG), exist_ok=True)
        with open(_LOG, "a", encoding="utf-8") as handle:
            handle.write("sidebar: " + message.rstrip() + "\n")
    except Exception:
        pass


class _Clicked(unohelper.Base, XActionListener):
    """One control's action listener, holding what that control does."""

    def __init__(self, run):
        self._run = run

    def actionPerformed(self, event):
        self._run()

    def disposing(self, event):
        pass


class Panel(unohelper.Base, XUIElement, XWindowListener,
            XTreeExpansionListener, XMouseListener):
    """One sidebar panel: the window, its contents, and what its buttons do."""

    def __init__(self, ctx, frame, parent, resource_url):
        self.ctx = ctx
        self.frame = frame
        self.resource_url = resource_url
        self.smgr = ctx.ServiceManager
        self.toolkit = self.smgr.createInstanceWithContext("com.sun.star.awt.Toolkit", ctx)
        self._value_controls = {}
        self._buttons = {}
        self._headline = None
        self._tree = None
        self._tree_heading = None
        self._tree_data = None
        self._collapsed = panel_rules.STARTS_COLLAPSED
        #: Button listeners, held so they are not collected out from under their buttons.
        self._listeners = []
        #: Folders whose items have been fetched, so reopening one does not append them twice.
        self._loaded_folders = set()
        self.window = None
        self._sx = self._sy = 1.0
        self._build(parent)
        self.refresh()

    # -- building ----------------------------------------------------------

    def _control(self, service, name, container, **props):
        """One control and its model, added to the container under ``name``."""
        model = self.smgr.createInstanceWithContext(
            "com.sun.star.awt.UnoControl%sModel" % service, self.ctx)
        for key, value in props.items():
            model.setPropertyValue(key, value)
        control = self.smgr.createInstanceWithContext(
            "com.sun.star.awt.UnoControl%s" % service, self.ctx)
        control.setModel(model)
        container.addControl(name, control)
        return control

    def _tree_control(self, name, container):
        """The navigator's tree.

        Not built through :meth:`_control`: a tree is not one of the ``UnoControl*`` family, it
        is ``com.sun.star.awt.tree.TreeControl`` with its own model, and its contents come from a
        separate ``XTreeDataModel`` rather than from properties. A UNO tree has exactly one root,
        so ``RootDisplayed`` is off and PLM's several top-level folders hang off an invisible one.
        """
        model = self.smgr.createInstanceWithContext(
            "com.sun.star.awt.tree.TreeControlModel", self.ctx)
        self._tree_data = self.smgr.createInstanceWithContext(
            "com.sun.star.awt.tree.MutableTreeDataModel", self.ctx)
        model.setPropertyValue("DataModel", self._tree_data)
        model.setPropertyValue("RootDisplayed", False)
        model.setPropertyValue("ShowsHandles", True)
        model.setPropertyValue("ShowsRootHandles", True)
        model.setPropertyValue("Editable", False)
        model.setPropertyValue(
            "SelectionType", uno.Enum("com.sun.star.view.SelectionType", "SINGLE"))

        control = self.smgr.createInstanceWithContext(
            "com.sun.star.awt.tree.TreeControl", self.ctx)
        control.setModel(model)
        container.addControl(name, control)
        control.addTreeExpansionListener(self)
        control.addMouseListener(self)
        return control

    def _build(self, parent):
        container = self.smgr.createInstanceWithContext(
            "com.sun.star.awt.UnoControlContainer", self.ctx)
        model = self.smgr.createInstanceWithContext(
            "com.sun.star.awt.UnoControlContainerModel", self.ctx)
        container.setModel(model)
        container.createPeer(self.toolkit, parent)

        # A button, not a label: the document half folds away behind it, and a button is the
        # one control the toolkit offers that says "this can be clicked" and takes the keyboard.
        self._headline = self._control("Button", "headline", container,
                                       Label="", FocusOnClick=False)
        self._listen(self._headline, self._toggle_document)

        for index, (label, _key) in enumerate(panel_rules.ROWS):
            self._control("FixedText", "label%d" % index, container, Label=label + ":")
            self._value_controls[label] = self._control(
                "FixedText", "value%d" % index, container, Label=panel_rules.ABSENT)

        for label, command, _rule in panel_rules.BUTTONS:
            button = self._control("Button", "btn_" + command, container,
                                   Label=label, Enabled=False)
            self._listen(button, lambda c=command: self._run_command(c))
            self._buttons[command] = button

        self._tree_heading = self._control("FixedText", "tree_heading", container,
                                           Label="Navigator")
        self._tree = self._tree_control("tree", container)

        container.addWindowListener(self)
        # Laid out through self.window, which every later call also uses, so it has to be set
        # before the first layout and not after _build returns.
        self.window = container
        self._measure(container)
        self._lay_out(container.getPosSize())
        return container

    def _measure(self, container):
        """How many pixels an appfont unit is here, which is the user's DPI and font size.

        Asking the window rather than assuming is the whole point: the same panel is drawn on a
        4K display and a laptop screen, and a number that looks right on one is unreadable on the
        other.
        """
        self._sx = self._sy = 1.0
        try:
            probe = Size()
            probe.Width = probe.Height = 100
            pixels = container.convertSizeToPixel(probe, MeasureUnit.APPFONT)
            if pixels.Width > 0 and pixels.Height > 0:
                self._sx = pixels.Width / 100.0
                self._sy = pixels.Height / 100.0
        except Exception:
            # Left at 1.0, which is wrong but readable, rather than failing to draw at all.
            _log("could not convert appfont to pixels\n%s" % traceback.format_exc())

    def _lay_out(self, size):
        """Place everything for the current width. The sidebar can be dragged to any width."""
        if self.window is None:
            return

        # Everything below is pixels: the constants are appfont, the window is not.
        margin = int(_MARGIN * self._sx)
        row = int(_ROW_H * self._sy)
        gap = int(_GAP * self._sy)
        label_w = int(_LABEL_W * self._sx)
        button_h = int(_BUTTON_H * self._sy)

        width = max(size.Width, margin * 4)
        y = margin

        self._headline.setPosSize(margin, y, width - 2 * margin, button_h, _POSSIZE)
        y += button_h + gap

        # Folded, the rows and the buttons are hidden and not laid out at all: the tree then
        # starts straight under the header and takes the whole panel, which is the point of it.
        container = self.window
        for index, (_label, _key) in enumerate(panel_rules.ROWS):
            label = container.getControl("label%d" % index)
            value = container.getControl("value%d" % index)
            label.setVisible(not self._collapsed)
            value.setVisible(not self._collapsed)
            if self._collapsed:
                continue
            label.setPosSize(margin, y, label_w, row, _POSSIZE)
            value.setPosSize(margin + label_w, y,
                             max(width - margin * 2 - label_w, margin), row, _POSSIZE)
            y += row + gap

        if not self._collapsed:
            y += gap * 2
        for _label, command, _rule in panel_rules.BUTTONS:
            button = self._buttons[command]
            button.setVisible(not self._collapsed)
            if self._collapsed:
                continue
            button.setPosSize(margin, y, width - 2 * margin, button_h, _POSSIZE)
            y += button_h + gap

        # The tree takes whatever height is left below the buttons. The sidebar can be dragged
        # to any size, so "what is left" is the only honest number; below a floor it would show
        # one clipped row, which reads as a broken control rather than a short one.
        y += gap * 2
        self._tree_heading.setPosSize(margin, y, width - 2 * margin, row, _POSSIZE)
        y += row + gap
        tree_h = max(size.Height - y - margin, int(_TREE_MIN_H * self._sy))
        self._tree.setPosSize(margin, y, width - 2 * margin, tree_h, _POSSIZE)

    # -- what it shows -----------------------------------------------------

    def refresh(self):
        """Ask the service about the document in front of us and show the answer."""
        try:
            document, state, user = self._current()
            self._headline.setLabel(panel_rules.document_header(
                state, self._collapsed, has_document=document is not None))
            for label, value in panel_rules.rows_for(state):
                self._value_controls[label].setText(value)

            allowed = panel_rules.enabled_buttons(state, user)
            for command, button in self._buttons.items():
                button.getModel().setPropertyValue("Enabled", command in allowed)
        except Exception:
            _log("refresh failed\n%s" % traceback.format_exc())

        self._load_tree()

    def _load_tree(self):
        """Fill the navigator with the folders this user may read.

        Kept apart from the rest of :meth:`refresh` on purpose: the tree is about the vault, not
        about the document in front of you, so a document that PLM has never seen still gets a
        navigator, and a navigator that cannot load still leaves the rows above it correct.
        """
        if self._tree is None:
            return
        try:
            answer = Client().folders()
            roots = navigator_rules.tree_from(answer.get("folders"))

            # A fresh data model every load, rather than a new root on the old one. Measured:
            # setRoot on a model the control is already showing leaves the previous root in
            # place, so the panel drew the whole vault twice after its second refresh.
            self._tree_data = self.smgr.createInstanceWithContext(
                "com.sun.star.awt.tree.MutableTreeDataModel", self.ctx)
            # A reload is a new set of nodes, so what was fetched into the old ones is gone too.
            self._loaded_folders = set()
            root = self._tree_data.createNode("Nexus PLM", True)
            for node in roots:
                root.appendChild(self._node_for(node))
            self._tree_data.setRoot(root)
            self._tree.getModel().setPropertyValue("DataModel", self._tree_data)
            # Re-asserted after the data model, not only at build time: the control reads it
            # when it takes a model, and a tree set up before it had one showed its root.
            self._tree.getModel().setPropertyValue("RootDisplayed", False)
            try:
                self._tree.expandNode(root)
            except Exception:
                # Nothing to expand when the vault is empty; not worth a log line.
                pass

            if not roots:
                self._tree_heading.setText("Navigator — nothing to show")
            else:
                self._tree_heading.setText("Navigator")
        except Exception:
            # A navigator that cannot load says so in its own heading rather than emptying
            # itself silently, which is indistinguishable from a vault with no folders.
            self._tree_heading.setText("Navigator — could not load")
            _log("tree failed\n%s" % traceback.format_exc())

    def _node_for(self, node):
        """One folder as a tree node, with its subfolders under it.

        Its items are not fetched here. A folder carries its ``folder_id`` as the node's data
        value so that expanding it can ask for them — one call per folder the user actually
        opens, rather than one per folder in the vault every time the panel draws.
        """
        made = self._tree_data.createNode(node["label"],
                                          navigator_rules.wants_children(node))
        # pyuno exposes this as an attribute, not a setter: setDataValue does not exist.
        made.DataValue = navigator_rules.ref(navigator_rules.FOLDER, node["id"])
        for child in node["children"]:
            made.appendChild(self._node_for(child))
        return made

    # -- XTreeExpansionListener --------------------------------------------

    def requestChildNodes(self, event):
        """Fill a folder with what is in it, the first time it is opened.

        Only fires for a node built with children "on demand", which is every folder the server
        said is not empty.
        """
        try:
            node = event.Node
            kind, folder_id = navigator_rules.parse_ref(node.DataValue)
            if kind != navigator_rules.FOLDER or folder_id in self._loaded_folders:
                return
            self._loaded_folders.add(folder_id)

            answer = Client().folder_items(folder_id)
            items = answer.get("items") or []
            for item in items:
                child = self._tree_data.createNode(navigator_rules.item_label(item), False)
                # The item's own id, so opening it needs no second lookup. The reference says
                # which kind it is: a folder id and an object id are both opaque strings, and a
                # double-click that cannot tell them apart would try to open a folder.
                child.DataValue = navigator_rules.ref(
                    navigator_rules.ITEM, item.get("plm_object_id"))
                node.appendChild(child)

            if not items:
                # Say so rather than opening onto nothing: an empty branch reads as a failed
                # load, and the count beside the folder promised something was there.
                node.appendChild(self._tree_data.createNode("(empty)", False))
        except Exception:
            _log("folder contents failed\n%s" % traceback.format_exc())

    # -- XMouseListener ----------------------------------------------------

    def mousePressed(self, event):
        """Open the item under a double-click.

        A double-click is what opens a document everywhere else in PLM, and a tree has no other
        obvious gesture: a single click has to stay free for selecting, and the expand handles
        already own the click that opens a folder.
        """
        try:
            if event.ClickCount < 2:
                return
            # What was clicked, not what is selected. getSelection() on this control answers
            # None even with a row plainly highlighted - measured on 26.2 - and acting on the
            # click's own position is the more honest reading of the gesture anyway.
            node = self._tree.getNodeForLocation(event.X, event.Y)
            if node is None:
                return
            kind, object_id = navigator_rules.parse_ref(node.DataValue)
            # A folder's double-click is LibreOffice's own expand, and "(empty)" is not anything.
            if kind != navigator_rules.ITEM:
                return
            self._open_item(object_id, node.DisplayValue)
        except Exception:
            _log("tree double-click failed\n%s" % traceback.format_exc())

    def mouseReleased(self, event):
        pass

    def mouseEntered(self, event):
        pass

    def mouseExited(self, event):
        pass

    def _open_item(self, object_id, label):
        """Stage an item's document and open it, the way every other open here works."""
        from nexusplm import document as doc
        from nexusplm import state

        client = Client()
        answer = client.stage(object_id)
        if not answer.get("success"):
            reason = answer.get("error") or "That item could not be opened."
            client.notify("%s — %s" % (label, reason), "warning")
            _log("open from tree refused: %s" % reason)
            return

        path = answer.get("file_path")
        if not path:
            client.notify("%s has no document in the vault." % label, "warning")
            return

        # Which item this file is, before it is opened: every PLM command keys off the path, and
        # a staged file opened without writing that down is one on which they all then refuse.
        state.remember(path, object_id, object_id=object_id)
        doc.open_staged(self.ctx, path)
        _log("opened %s from the tree as %s" % (path, object_id))
        self.refresh()

    def treeExpanding(self, event):
        pass

    def treeCollapsing(self, event):
        pass

    def treeExpanded(self, event):
        pass

    def treeCollapsed(self, event):
        pass

    def _current(self):
        """(document, state answer, signed-in user) for whatever is in front of the panel."""
        from nexusplm import document as doc

        document = doc.current(self.ctx)
        if document is None:
            return None, None, None

        url = getattr(document, "URL", "") or ""
        path = unohelper.fileUrlToSystemPath(url) if url.startswith("file:") else None
        if not path:
            return document, None, None

        client = Client()
        state = client.state(file_path=path)
        try:
            user = (client.me() or {}).get("username")
        except Exception:
            user = None
        return document, state, user

    # -- what its buttons do -----------------------------------------------

    def _listen(self, control, run):
        """Give a control its own listener, and keep a reference to it.

        A listener per control, rather than one listener working out which control an event came
        from. Both of the obvious ways to do the latter fail here, measured: pyuno hands back a
        fresh proxy for the same UNO object on every ``getModel()``, so ``is`` between two of them
        is false even for a single control; and ``Tag``, the obvious place to label a model, is
        not a property of ``UnoControlButtonModel`` — ``setPropertyValue`` accepted it and reading
        it back threw ``UnknownPropertyException``.

        Nothing else holds the listener, and a collected one stops its button working silently.
        """
        listener = _Clicked(run)
        self._listeners.append(listener)
        control.addActionListener(listener)

    def _toggle_document(self):
        """Fold the document half away, or bring it back."""
        self._collapsed = not self._collapsed
        # Laid out again before repainting, or the tree keeps the height it had and the rows
        # land on top of it.
        self._lay_out(self.window.getPosSize())
        self.refresh()

    def _run_command(self, command):
        """Dispatch the same script URL the toolbar and menu use, so behaviour cannot diverge."""
        try:
            self._dispatch(command)
            self.refresh()
        except Exception:
            _log("button %s failed\n%s" % (command, traceback.format_exc()))

    def _dispatch(self, command):
        transformer = self.smgr.createInstanceWithContext(
            "com.sun.star.util.URLTransformer", self.ctx)
        url = uno.createUnoStruct("com.sun.star.util.URL")
        url.Complete = SCRIPT % command
        _, url = transformer.parseStrict(url)
        dispatch = self.frame.queryDispatch(url, "", 0)
        if dispatch is None:
            _log("nothing will dispatch %s" % command)
            return
        dispatch.dispatch(url, ())

    # -- XWindowListener ---------------------------------------------------

    def windowResized(self, event):
        self._lay_out(Rectangle(0, 0, event.Width, event.Height))

    def windowMoved(self, event):
        pass

    def windowShown(self, event):
        self.refresh()

    def windowHidden(self, event):
        pass

    def disposing(self, event):
        pass

    # -- XUIElement --------------------------------------------------------

    def getRealInterface(self):
        return self.window

    def getFrame(self):
        return self.frame

    def getResourceURL(self):
        return self.resource_url

    def getType(self):
        return TOOLPANEL


class PanelFactory(unohelper.Base, XUIElementFactory, XServiceInfo):
    """Answers LibreOffice when it asks for private:resource/toolpanel/NexusPLMPanelFactory/..."""

    def __init__(self, ctx):
        self.ctx = ctx

    def createUIElement(self, resource_url, args):
        try:
            values = {a.Name: a.Value for a in args}
            frame = values.get("Frame")
            parent = values.get("ParentWindow")
            if frame is None or parent is None:
                _log("createUIElement without a %s"
                     % ("Frame" if frame is None else "ParentWindow"))
                return None
            # One line, because "was the factory asked at all" is the first question every time
            # the deck comes up empty, and it is otherwise unanswerable from outside.
            _log("building the panel for %s" % values.get("ApplicationName", "?"))
            return Panel(self.ctx, frame, parent, resource_url)
        except Exception:
            # A factory that throws takes the sidebar down with it; an empty deck is survivable.
            _log("createUIElement failed\n%s" % traceback.format_exc())
            return None

    def getImplementationName(self):
        return FACTORY_IMPLEMENTATION

    def supportsService(self, name):
        return name == FACTORY_SERVICE

    def getSupportedServiceNames(self):
        return (FACTORY_SERVICE,)


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(PanelFactory, FACTORY_IMPLEMENTATION, (FACTORY_SERVICE,))

# The script provider scans this folder too; there is nothing here to offer as a macro.
g_exportedScripts = ()
