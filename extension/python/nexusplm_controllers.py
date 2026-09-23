"""The UNO component behind the toolbar's stacked buttons.

A toolbar button that opens a menu — Save ▾, Tasks ▾, Values ▾ — is not something Addons.xcu can
describe on its own. What makes one is a *toolbar controller* registered against the button's
command URL (Controller.xcu): when the toolbar is built, LibreOffice sees that the command has a
controller and hands the button to it. This file is that controller, once, serving every stacked
button by the command it was created for. Pressing the button opens a popup menu of the group's
commands under it.

It is loaded by LibreOffice's Python component loader, not by the script provider that runs
``nexus_commands.py`` — the manifest names it as a UNO component. The loader sets ``__file__`` and
puts ``pythonpath/`` beside it on ``sys.path``, so the shared package imports as usual. The
``g_exportedScripts`` at the bottom is empty so the script provider, which also scans this folder,
offers nothing from here as a macro.

Choosing an entry dispatches the same ``vnd.sun.star.script:`` URL the flat toolbar and the menu
use, through the frame, so a command behaves identically wherever it was reached from.
"""

import os
import traceback

import uno
import unohelper
from com.sun.star.awt import XMenuListener, Rectangle
from com.sun.star.beans import PropertyValue
from com.sun.star.frame import XPopupMenuController, XStatusListener, XToolbarController
from com.sun.star.lang import XInitialization, XServiceInfo
from com.sun.star.util import XUpdatable

IMPLEMENTATION_NAME = "com.nexusplm.libreoffice.PopupController"
SERVICE_NAMES = ("com.sun.star.frame.ToolbarController", "com.sun.star.frame.PopupMenuController")

# com.sun.star.lang.SystemDependent.SYSTEM_WIN32, for asking a window for its native handle.
_SYSTEM_WIN32 = 1

SCRIPT = ("vnd.sun.star.script:NexusPLM.oxt|python|nexus_commands.py$%s"
          "?language=Python&location=user:uno_packages")

#: What each stacked button opens: (title, function, icon), or None for a separator. The icon is
#: the same file the command shows on the toolbar, at 16px, which is the size a menu wants. The
#: entries are the same commands as the flat menu, in the same order, so the two never disagree
#: about what exists.
STACKS = {
    "nexusplm:account": [
        ("Sign In...", "sign_in", "SignIn"),
        ("Sign Out", "sign_out", "SignOut"),
    ],
    "nexusplm:save": [
        ("Save to PLM", "save_to_plm", "Save"),
        ("Save As New Item...", "save_as_new", "SaveAs"),
        ("Save As Existing Item...", "save_as_existing", "SaveAsExisting"),
    ],
    "nexusplm:tasks": [
        ("Check Out", "check_out", "CheckOut"),
        ("Check In...", "check_in", "CheckIn"),
        None,
        ("Release", "release", "Release"),
        ("Revise", "revise", "Revise"),
        None,
        ("Change Ownership...", "change_owner", "ChangeOwner"),
    ],
    "nexusplm:workflow": [
        ("My Worklist...", "worklist", "MyWorkList"),
        ("New Workflow...", "new_workflow", "NewWorkflow"),
    ],
    "nexusplm:values": [
        ("Edit Values...", "edit_values", "EditValues"),
        ("Refresh Values", "refresh_values", "RefreshValues"),
        None,
        ("Reload Document", "reload_document", "Reload"),
    ],
    "nexusplm:about": [
        ("Current Settings...", "settings", "Settings"),
        ("Connection Status", "connection_status", "ConnectionStatus"),
        None,
        ("Help", "help_site", "Help"),
        ("About NexusPLM...", "about", "Nexus"),
    ],
}

_LOG = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                    "NexusPLM", "Logs", "plmlibreofficeaddin.log")


def _log(message):
    try:
        os.makedirs(os.path.dirname(_LOG), exist_ok=True)
        with open(_LOG, "a", encoding="utf-8") as handle:
            handle.write("controller: " + message.rstrip() + "\n")
    except Exception:
        pass


class PopupController(unohelper.Base, XToolbarController, XPopupMenuController, XInitialization,
                      XServiceInfo, XMenuListener, XStatusListener, XUpdatable):
    """One instance per stacked button on each toolbar, created by LibreOffice from Controller.xcu.

    Implements both controller shapes LibreOffice knows: the toolbar controller, which is what
    add-on toolbar items are actually built with, and the popup-menu controller, which the Tabbed
    UI and module toolbars use for dropdowns. Whichever way it is asked, the answer is the same menu.
    """

    #: Icons, once per office session rather than once per menu: name -> XGraphic.
    _graphics = {}

    def __init__(self, context, *args):
        self.context = context
        self.frame = None
        self.parent_window = None
        self.command = ""
        self.menu = None
        self.entries = []
        # The toolbar factory hands its arguments to the constructor — unohelper calls
        # clazz(context, *args) — while the popup-menu factory calls initialize() afterwards.
        # Taking both keeps one class serving both, and a constructor that refuses the extra
        # arguments does not just fail this button: it takes the whole toolbar down with it.
        if args:
            self.initialize(args)

    # ── XInitialization: LibreOffice tells us which button we are ─────────

    def initialize(self, args):
        for arg in args:
            name = getattr(arg, "Name", None)
            if name == "Frame":
                self.frame = arg.Value
            elif name == "CommandURL":
                self.command = arg.Value
            elif name == "ParentWindow":
                self.parent_window = arg.Value
        self.entries = STACKS.get(self.command, [])
        if not self.entries:
            _log("no stack defined for command %r" % self.command)

    # ── XToolbarController: the button itself ─────────────────────────────

    def execute(self, modifiers):
        self._show_menu()

    def click(self):
        self._show_menu()

    def doubleClick(self):
        pass

    def createPopupWindow(self):
        # The arrow half of a dropdown button asks for a window; showing the menu here and
        # answering "no window" gives the same result and keeps one code path.
        self._show_menu()
        return None

    def createItemWindow(self, parent):
        return None

    def update(self):
        pass

    def _show_menu(self):
        try:
            menu = self.context.ServiceManager.createInstanceWithContext(
                "com.sun.star.awt.PopupMenu", self.context)
            self.setPopupMenu(menu)
            rect = self._button_rect()
            # PopupMenuDirection.EXECUTE_DOWN = 1: the menu hangs off the button's lower edge.
            menu.execute(self._peer(), rect, 1)
        except Exception:
            _log("could not show the menu for %s\n%s" % (self.command, traceback.format_exc()))

    def _peer(self):
        """The window the menu is shown over: the application window, because that is the one whose
        client coordinates the pointer can be converted into."""
        if self.frame is not None:
            return self.frame.getContainerWindow()
        return self.parent_window

    def _button_rect(self):
        """Where the menu should hang from, in the coordinates of the window it is shown over.

        LibreOffice tells a toolbar controller which toolbar it is on, but not where on that
        toolbar its own button sits — and the toolbar window it hands over is a bare XWindow2 with
        neither a native handle nor an accessible context to locate itself by. The pointer is on
        the button when this runs, so the menu is anchored to the pointer instead, converted into
        the application window's client coordinates. Without it the menu appeared at the window's
        top-left corner, whichever button was pressed.
        """
        rect = Rectangle()
        rect.Width, rect.Height = 1, 1
        try:
            import ctypes
            import ctypes.wintypes
            point = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            ctypes.windll.user32.ScreenToClient(
                ctypes.windll.user32.GetForegroundWindow(), ctypes.byref(point))
            # A little left of the pointer and below it, so the menu reads as belonging to the
            # button rather than covering it.
            rect.X = max(0, point.x - 12)
            rect.Y = point.y + 14
        except Exception:
            _log("could not place the menu under the pointer\n" + traceback.format_exc())
        return rect

    # ── icons ─────────────────────────────────────────────────────────────

    def _icons_url(self):
        """Where this extension's icons live, as a URL.

        Asked of the deployment singleton rather than worked out from ``__file__``: the extension
        is unpacked into a cache folder whose name changes on every install, and this is the
        supported way to find one's own files. (``__file__`` would work here — a UNO component is
        loaded by pythonloader, which sets it — but it does not in ``nexus_commands.py``, which the
        script provider exec()s, so this is the habit worth keeping.)
        """
        provider = self.context.getByName(
            "/singletons/com.sun.star.deployment.PackageInformationProvider")
        return provider.getPackageLocation("com.nexusplm.libreoffice") + "/icons"

    def _graphic(self, name):
        """The icon called ``name``, or ``None`` when it cannot be loaded.

        The 50px file, not the 16px or 26px ones the toolbar uses: LibreOffice is told not to
        scale a menu image, so the file's own size is the size on screen, and at 16px next to 13pt
        text an icon reads as a smudge.

        A missing icon costs the entry its picture and nothing else: an exception here would take
        the whole menu with it.
        """
        if name in PopupController._graphics:
            return PopupController._graphics[name]

        graphic = None
        try:
            url = PropertyValue()
            url.Name, url.Value = "URL", "%s/%s_50.png" % (self._icons_url(), name)
            provider = self.context.ServiceManager.createInstanceWithContext(
                "com.sun.star.graphic.GraphicProvider", self.context)
            graphic = provider.queryGraphic((url,))
        except Exception:
            _log("could not load the icon %r\n%s" % (name, traceback.format_exc()))

        PopupController._graphics[name] = graphic
        return graphic

    # ── XPopupMenuController: fill a menu ─────────────────────────────────

    def setPopupMenu(self, popup_menu):
        self.menu = popup_menu
        try:
            popup_menu.clear()
            item_id = 1
            for entry in self.entries:
                if entry is None:
                    popup_menu.insertSeparator(-1)
                    continue
                title, function, icon = entry
                popup_menu.insertItem(item_id, title, 0, -1)
                popup_menu.setCommand(item_id, SCRIPT % function)

                graphic = self._graphic(icon)
                if graphic is not None:
                    # False: keep the icon at the size it was drawn, rather than letting the menu
                    # shrink it back to its own default.
                    popup_menu.setItemImage(item_id, graphic, False)

                item_id += 1
            popup_menu.addMenuListener(self)
        except Exception:
            _log("setPopupMenu failed for %s\n%s" % (self.command, traceback.format_exc()))

    def updatePopupMenu(self):
        # Every entry stays enabled: what the service refuses, it explains in its own words, which
        # is more use than a greyed button that says nothing.
        pass

    # ── XMenuListener: an entry was chosen ────────────────────────────────

    def itemSelected(self, event):
        try:
            url = self.menu.getCommand(event.MenuId)
            if url:
                self._dispatch(url)
        except Exception:
            _log("itemSelected failed for %s\n%s" % (self.command, traceback.format_exc()))

    def itemHighlighted(self, event): pass
    def itemActivated(self, event): pass
    def itemDeactivated(self, event): pass

    def _dispatch(self, url_text):
        """Runs the chosen command exactly as the flat toolbar would: a frame dispatch of its URL."""
        transformer = self.context.ServiceManager.createInstanceWithContext(
            "com.sun.star.util.URLTransformer", self.context)
        url = uno.createUnoStruct("com.sun.star.util.URL")
        url.Complete = url_text
        _, url = transformer.parseStrict(url)
        dispatch = self.frame.queryDispatch(url, "", 0)
        if dispatch is None:
            _log("nothing will dispatch %s" % url_text)
            return
        dispatch.dispatch(url, ())

    # ── XStatusListener / XEventListener: nothing to track ────────────────

    def statusChanged(self, event): pass
    def disposing(self, event): pass

    # ── XServiceInfo ──────────────────────────────────────────────────────

    def getImplementationName(self):
        return IMPLEMENTATION_NAME

    def supportsService(self, name):
        return name in SERVICE_NAMES

    def getSupportedServiceNames(self):
        return SERVICE_NAMES


# What the Python component loader looks for.
g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(PopupController, IMPLEMENTATION_NAME, SERVICE_NAMES)

# The script provider scans this folder too; there is nothing here to offer as a macro.
g_exportedScripts = ()
