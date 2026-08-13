#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
GTK4 editor for .desktop files.

Visual style is modelled after KDE's KMenuEdit:
  * left  : searchable list of installed applications
  * right : "General" column (icon / name / description) next to a
            "Command" column (executable, work path, run-in-terminal)
  * bottom: action bar (New / Delete / Save As / Save / Close)
"""

import configparser
import os
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

APP_ID = "io.github.hyprmenu.desktop-editor"

XDG_DATA_DIRS = [
    Path.home() / ".local/share/applications",
    Path.home() / ".local/share/flatpak/exports/share/applications",
    Path("/var/lib/flatpak/exports/share/applications"),
    Path("/usr/local/share/applications"),
    Path("/usr/share/applications"),
    Path.home() / ".nix-profile/share/applications",
    Path("/run/current-system/sw/share/applications"),
]

USER_APPS_DIR = Path.home() / ".local/share/applications"

KEY_ORDER = [
    "Type", "Name", "GenericName", "Comment", "Icon", "Exec", "TryExec",
    "Path", "Terminal", "StartupNotify", "StartupWMClass", "Categories",
    "Keywords", "MimeType", "Actions", "DBusActivatable",
    "PrefersNonDefaultGPU", "NoDisplay", "Hidden",
    "X-GNOME-Autostart-enabled", "Version",
]

# key, label, kind, group. kind in {"entry", "enum", "bool"}
FIELD_SPECS = [
    ("Name", "Name", "entry", "general"),
    ("GenericName", "GenericName", "entry", "general"),
    ("Comment", "Comment", "entry", "general"),
    ("Exec", "Exec", "entry", "command"),
    ("Path", "Work path", "entry", "command"),
    ("Terminal", "Run in terminal", "bool", "command"),
    ("StartupNotify", "Startup notification", "bool", "command"),
    ("Type", "Type", "enum", "advanced"),
    ("TryExec", "TryExec", "entry", "advanced"),
    ("StartupWMClass", "Startup WM class", "entry", "advanced"),
    ("Categories", "Categories", "entry", "advanced"),
    ("Keywords", "Keywords", "entry", "advanced"),
    ("MimeType", "MIME types", "entry", "advanced"),
    ("Actions", "Actions", "entry", "advanced"),
    ("Version", "Version", "entry", "advanced"),
    ("DBusActivatable", "DBus activatable", "bool", "advanced"),
    ("PrefersNonDefaultGPU", "Prefers non-default GPU", "bool", "advanced"),
    ("X-GNOME-Autostart-enabled", "Autostart enabled", "bool", "advanced"),
]

BOOL_KEYS = {
    "Terminal", "StartupNotify", "NoDisplay", "Hidden",
    "DBusActivatable", "PrefersNonDefaultGPU", "X-GNOME-Autostart-enabled",
}

TYPE_CHOICES = ["Application", "Link", "Directory"]

CSS = b"""
window.desktop-editor {
    background-color: #eff0f1;
    color: #31363b;
}
headerbar {
    background-color: #fcfcfc;
    border-bottom: 1px solid #d8dcde;
}
.sidebar {
    background-color: #f7f8f8;
    border-right: 1px solid #d8dcde;
}
.sidebar list,
.sidebar listview {
    background-color: #f7f8f8;
}
.sidebar row {
    border-radius: 6px;
    margin: 2px 6px;
    padding: 2px 4px;
    background-color: transparent;
}
.sidebar row:selected {
    background-color: #3daee9;
    color: #ffffff;
}
.sidebar row:selected label { color: #ffffff; }
.sidebar row label.dim-label { color: #6f7a80; }
.sidebar row:selected label.dim-label { color: #d5f2ff; }
.panel {
    background-color: #fcfcfc;
    border: 1px solid #d8dcde;
    border-radius: 8px;
}
.panel-label {
    color: #3daee9;
    font-weight: 600;
    padding-top: 6px;
    padding-bottom: 2px;
}
.field-name {
    font-weight: 500;
}
.footer {
    background-color: #fcfcfc;
    border-top: 1px solid #d8dcde;
}
.icon-picker button {
    padding: 6px 14px;
}
.icon-picker .picker-icon {
    padding: 12px;
}
"""


class DesktopEntry:
    """Thin, order-preserving wrapper around configparser for .desktop files."""

    def __init__(self, path):
        self.path = Path(path)
        self.parser = configparser.RawConfigParser(
            strict=False,
            empty_lines_in_values=False,
            allow_no_value=False,
        )
        self.parser.optionxform = str  # keep key case (StartupWMClass etc.)

    @classmethod
    def parse(cls, path):
        entry = cls(path)
        with open(path, "r", encoding="utf-8-sig") as fh:
            try:
                entry.parser.read_file(fh)
            except configparser.Error as exc:
                raise ValueError(f"{path.name}: {exc}")
        if not entry.parser.has_section("Desktop Entry"):
            raise ValueError(f"{path.name} has no [Desktop Entry] section")
        return entry

    def get(self, key, section="Desktop Entry"):
        if not self.parser.has_section(section):
            return None
        return self.parser.get(section, key, fallback=None)

    def set(self, key, value, section="Desktop Entry"):
        if not self.parser.has_section(section):
            self.parser.add_section(section)
        if value is None:
            self.parser.remove_option(section, key)
        else:
            self.parser.set(section, key, str(value))

    def main_options(self):
        if self.parser.has_section("Desktop Entry"):
            return list(self.parser.items("Desktop Entry"))
        return []

    def other_sections(self):
        return [s for s in self.parser.sections() if s != "Desktop Entry"]

    def save(self, path=None):
        path = Path(path) if path else self.path
        if not self.parser.has_section("Desktop Entry"):
            self.parser.add_section("Desktop Entry")
        sec = self.parser["Desktop Entry"]
        ordered = {k: sec.pop(k) for k in KEY_ORDER if k in sec}
        for k, v in sec.items():
            ordered[k] = v
        sec.clear()
        sec.update(ordered)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            self.parser.write(fh)
        os.replace(tmp, path)
        self.path = path


def bool_from_str(value):
    return str(value).strip().lower() in ("true", "1", "yes", "on")


class AppRow(Gtk.ListBoxRow):
    """List row carrying the application item it renders."""

    def __init__(self, item):
        super().__init__()
        self.item = item
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1,
                      margin_top=4, margin_bottom=4)
        name = Gtk.Label(label=item["name"], xalign=0, halign=Gtk.Align.START,
                         ellipsize=Pango.EllipsizeMode.END)
        box.append(name)
        if item["summary"]:
            summary = Gtk.Label(label=item["summary"], xalign=0,
                                halign=Gtk.Align.START,
                                ellipsize=Pango.EllipsizeMode.END)
            summary.add_css_class("dim-label")
            box.append(summary)
        self.set_child(box)


def iter_desktop_files():
    seen, out = set(), []
    for base in XDG_DATA_DIRS:
        if not base.is_dir():
            continue
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if not fn.endswith(".desktop"):
                    continue
                path = Path(root) / fn
                try:
                    rp = os.path.realpath(path)
                except OSError:
                    continue
                if rp == "/dev/null" or rp in seen:
                    continue
                seen.add(rp)
                out.append(path)
    return out


def build_item(path):
    name, summary = path.stem, ""
    try:
        entry = DesktopEntry.parse(path)
        name = entry.get("Name") or path.stem
        parts = [p for p in (entry.get("GenericName"), entry.get("Comment"),
                             entry.get("Exec")) if p]
        summary = " · ".join(parts)
    except Exception:
        summary = "(unreadable — opens as raw text)"
    return {
        "path": str(path),
        "base": path.name,
        "name": name,
        "summary": summary,
    }


class IconPickerDialog(Gtk.Window):
    """Searchable picker over every icon in the current theme, with a
    Browse… button for picking an icon from a file."""

    def __init__(self, parent, current, on_pick):
        super().__init__(title="Choose icon", transient_for=parent,
                         modal=True)
        self.on_pick = on_pick
        self.add_css_class("icon-picker")
        self.set_default_size(560, 520)

        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        names = sorted(icon_theme.get_icon_names())
        self.store = Gio.ListStore.new(Gtk.StringObject)
        for name in names:
            self.store.append(Gtk.StringObject.new(name))

        self.search = Gtk.SearchEntry(placeholder_text="Search icons…")
        self.search.connect("search-changed", self.on_search_changed)
        self.search.connect("activate", self.accept)
        self.search.set_hexpand(True)

        browse_btn = Gtk.Button(label="Browse…")
        browse_btn.connect("clicked", self.on_browse)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        top.append(self.search)
        top.append(browse_btn)

        self.filter = Gtk.CustomFilter.new(self.match, None)
        self.filtered = Gtk.FilterListModel.new(self.store, self.filter)
        self.selection = Gtk.SingleSelection.new(self.filtered)
        self.selection.set_autoselect(True)

        if current:
            for i in range(self.store.get_n_items()):
                if self.store.get_item(i).get_string() == current:
                    self.selection.select_item(i, True)
                    break

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self.on_factory_setup)
        factory.connect("bind", self.on_factory_bind)

        grid = Gtk.GridView.new(self.selection, factory)
        grid.set_min_columns(4)
        grid.set_max_columns(16)
        grid.connect("activate", self.on_grid_activate)
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.set_child(grid)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _b: self.close())
        select_btn = Gtk.Button(label="Select")
        select_btn.add_css_class("suggested-action")
        select_btn.connect("clicked", lambda _b: self.accept())
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                         halign=Gtk.Align.END)
        bottom.append(cancel_btn)
        bottom.append(select_btn)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                       margin_top=8, margin_bottom=8, margin_start=8,
                       margin_end=8)
        root.append(top)
        root.append(scrolled)
        root.append(bottom)
        self.set_child(root)

    def match(self, item, *_args):
        q = self.search.get_text().strip().lower()
        if not q:
            return True
        return q in item.get_string().lower()

    def on_search_changed(self, _entry):
        self.filter.changed(Gtk.FilterChange.DIFFERENT)

    def on_factory_setup(self, _factory, list_item):
        image = Gtk.Image(icon_size=Gtk.IconSize.LARGE)
        image.set_pixel_size(36)
        image.add_css_class("picker-icon")
        list_item.set_child(image)

    def on_factory_bind(self, _factory, list_item):
        image = list_item.get_child()
        image.set_from_icon_name(list_item.get_item().get_string())

    def on_grid_activate(self, _grid, _position):
        self.accept()

    def accept(self, *_args):
        item = self.selection.get_selected_item()
        if item is not None:
            self.on_pick(item.get_string())
        self.close()

    def on_browse(self, _btn):
        dialog = Gtk.FileDialog()
        dialog.set_title("Choose icon file")
        filt = Gtk.FileFilter()
        filt.set_name("Images")
        for pattern in ("*.png", "*.svg", "*.xpm", "*.jpg", "*.jpeg",
                        "*.webp", "*.ico", "*.bmp"):
            filt.add_pattern(pattern)
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(filt)
        dialog.set_filters(store)

        def cb(fd, result, _user_data):
            try:
                gfile = fd.open_finish(result)
            except GLib.Error as exc:
                if exc.matches(Gio.IOErrorEnum, Gio.IOErrorEnum.CANCELLED):
                    return
                return
            self.on_pick(gfile.get_path())
            self.close()

        dialog.open(self, None, cb, None)


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.window = None
        self.items = []
        self.current = None
        self.modified = False
        self._loading = False
        self._restoring = False
        self._bool_touched = set()
        self._last_row = None
        self.field_widgets = {}

    # ----------------------------------------------------------- actions

    def do_startup(self):
        Gtk.Application.do_startup(self)

        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        for name in ("new", "delete", "save", "save-as", "refresh", "about",
                     "quit"):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate",
                           getattr(self, f"on_action_{name.replace('-', '_')}"))
            self.add_action(action)
        self.set_accels_for_action("app.new", ["<Ctrl>n"])
        self.set_accels_for_action("app.save", ["<Ctrl>s"])
        self.set_accels_for_action("app.save-as", ["<Ctrl><Shift>s"])
        self.set_accels_for_action("app.refresh", ["F5"])
        self.set_accels_for_action("app.quit", ["<Ctrl>q"])

    def do_activate(self):
        if self.window is None:
            self.build_window()
            self.refresh()
        self.window.present()

    # ----------------------------------------------------------- window ui

    def build_window(self):
        win = Gtk.ApplicationWindow(application=self,
                                    default_width=1020, default_height=660)
        win.add_css_class("desktop-editor")
        self.window = win

        # header --------------------------------------------------------
        hb = Gtk.HeaderBar()
        title = Gtk.Label(label="Desktop Entry Editor",
                          halign=Gtk.Align.START, xalign=0)
        title.add_css_class("title")
        hb.set_title_widget(title)

        btn_refresh = Gtk.Button(icon_name="view-refresh")
        btn_refresh.set_tooltip_text("Reload application list (F5)")
        btn_refresh.connect("clicked", lambda _b: self.refresh())
        btn_about = Gtk.Button(icon_name="dialog-information")
        btn_about.set_tooltip_text("About")
        btn_about.connect("clicked", lambda _b: self.on_action_about(None, None))
        hb.pack_end(btn_about)
        hb.pack_end(btn_refresh)
        win.set_titlebar(hb)

        # layout --------------------------------------------------------
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_start_child(self.build_sidebar())
        paned.set_resize_start_child(False)
        paned.set_position(300)

        self.stack = Gtk.Stack()
        self.stack.add_named(self.build_form_page(), "form")
        self.stack.add_named(self.build_raw_page(), "raw")
        self.stack.set_hexpand(True)
        paned.set_end_child(self.stack)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(paned)
        root.append(self.build_footer())
        win.set_child(root)

    def build_sidebar(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                      margin_top=8, margin_bottom=8)
        box.add_css_class("sidebar")

        self.search = Gtk.SearchEntry(placeholder_text="Search applications…")
        self.search.set_margin_start(8)
        self.search.set_margin_end(8)
        self.search.connect("search-changed", self.on_search_changed)
        box.append(self.search)

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-selected", self.on_row_selected)
        self.listbox.set_filter_func(self.filter_func)
        scrolled.set_child(self.listbox)
        box.append(scrolled)

        self.count_label = Gtk.Label(xalign=0)
        self.count_label.add_css_class("dim-label")
        self.count_label.set_margin_start(10)
        box.append(self.count_label)
        return box

    def build_form_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                       margin_top=10, margin_bottom=10, margin_start=10,
                       margin_end=10)

        cols = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        # -- General column -------------------------------------------
        general = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        general.add_css_class("panel")
        general.set_size_request(300, -1)
        general.append(self.section_label("General"))

        icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12,
                           margin_start=12, margin_end=12)
        self.icon_preview = Gtk.Image(icon_name="application-x-executable")
        self.icon_preview.set_icon_size(Gtk.IconSize.LARGE)
        self.icon_preview.set_pixel_size(48)
        icon_box.append(self.icon_preview)

        icon_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        btn_icon = Gtk.Button(label="Choose…")
        btn_icon.connect("clicked", self.on_choose_icon)
        btn_icon.set_halign(Gtk.Align.START)
        self.icon_name_label = Gtk.Label(label="None", xalign=0,
                                         halign=Gtk.Align.START)
        self.icon_name_label.add_css_class("dim-label")
        self.icon_name_label.set_ellipsize(Pango.EllipsizeMode.END)
        icon_text.append(btn_icon)
        icon_text.append(self.icon_name_label)
        icon_text.set_hexpand(True)
        icon_box.append(icon_text)
        general.append(icon_box)

        self.general_grid = Gtk.Grid(column_spacing=8, row_spacing=6,
                                     margin_start=12, margin_end=12,
                                     margin_bottom=12)
        general.append(self.general_grid)

        self.chk_show_in_menu = Gtk.CheckButton(label="Show in menus")
        self.chk_hidden = Gtk.CheckButton(label="Hidden from launchers")
        for chk in (self.chk_show_in_menu, self.chk_hidden):
            chk.set_halign(Gtk.Align.START)
            chk.set_margin_start(12)
            chk.connect("toggled", self.on_bool_toggled)
        general.append(self.chk_show_in_menu)
        general.append(self.chk_hidden)

        cols.append(general)

        # -- Command column -------------------------------------------
        command = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        command.add_css_class("panel")
        command.set_vexpand(True)
        command.append(self.section_label("Command"))

        self.command_grid = Gtk.Grid(column_spacing=8, row_spacing=6,
                                     margin_start=12, margin_end=12,
                                     margin_bottom=12)
        command.append(self.command_grid)

        cols.append(command)
        page.append(cols)

        # -- Advanced -------------------------------------------------
        advanced = Gtk.Expander(label="Advanced")
        adv_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                          margin_top=6)
        self.adv_grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        adv_box.append(self.adv_grid)
        adv_box.append(self.build_custom_keys_box())
        adv_box.append(self.build_other_sections_box())
        advanced.set_child(adv_box)
        page.append(advanced)

        # build the standard field widgets -----------------------------
        row_count = {"general": 0, "command": 0, "advanced": 0}
        for key, label, kind, group in FIELD_SPECS:
            widget = self.make_field_widget(key, kind)
            self.field_widgets[key] = (kind, widget)

            container = widget
            if group == "command" and key in ("Exec", "Path"):
                container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                    spacing=6)
                container.append(widget)
                browse = Gtk.Button(label="Browse…")
                browse.connect("clicked", self.browse_exec if key == "Exec"
                               else self.browse_path)
                container.append(browse)

            grid = {"general": self.general_grid,
                    "command": self.command_grid,
                    "advanced": self.adv_grid}[group]
            grid.attach(self.field_name_label(label), 0, row_count[group], 1, 1)
            container.set_hexpand(True)
            grid.attach(container, 1, row_count[group], 1, 1)
            row_count[group] += 1

        return page

    def build_raw_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                       margin_top=12, margin_bottom=12, margin_start=12,
                       margin_end=12)
        hint = Gtk.Label(label="This file is not valid .desktop/INI syntax — "
                               "editing it as raw text. Changes are written "
                               "verbatim.",
                         halign=Gtk.Align.START, wrap=True)
        hint.add_css_class("dim-label")
        page.append(hint)
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        self.raw_view = Gtk.TextView(editable=True)
        self.raw_view.add_css_class("monospace")
        self.raw_view.get_buffer().connect("changed",
                                           lambda _b: self.mark_modified())
        scrolled.set_child(self.raw_view)
        page.append(scrolled)
        return page

    def build_custom_keys_box(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        label = Gtk.Label(label="Other properties", halign=Gtk.Align.START)
        label.add_css_class("panel-label")
        label.set_margin_top(8)
        box.append(label)

        self.custom_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        scrolled = Gtk.ScrolledWindow(min_content_height=140)
        scrolled.set_child(self.custom_list)
        box.append(scrolled)

        add_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.new_key_entry = Gtk.Entry(
            placeholder_text="Add property (e.g. Keywords[de])", hexpand=True)
        add_btn = Gtk.Button(label="Add")
        add_btn.connect("clicked", self.on_add_key)
        add_row.append(self.new_key_entry)
        add_row.append(add_btn)
        box.append(add_row)
        return box

    def build_other_sections_box(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        label = Gtk.Label(label="Other sections (kept as-is)",
                          halign=Gtk.Align.START)
        label.add_css_class("dim-label")
        box.append(label)
        scrolled = Gtk.ScrolledWindow(min_content_height=120)
        self.other_view = Gtk.TextView(editable=False)
        self.other_view.add_css_class("monospace")
        scrolled.set_child(self.other_view)
        box.append(scrolled)
        return box

    def build_footer(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                      margin_top=6, margin_bottom=6, margin_start=10,
                      margin_end=10)
        box.add_css_class("footer")

        left = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_new = Gtk.Button(label="New Entry")
        btn_new.connect("clicked", lambda _b: self.on_action_new(None, None))
        btn_delete = Gtk.Button(label="Delete Entry")
        btn_delete.connect("clicked", lambda _b: self.on_action_delete(None, None))
        left.append(btn_new)
        left.append(btn_delete)
        box.append(left)

        self.path_label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END,
                                    selectable=True, hexpand=True)
        self.path_label.add_css_class("dim-label")
        self.path_label.set_margin_start(12)
        box.append(self.path_label)

        right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_save_as = Gtk.Button(label="Save As…")
        btn_save_as.connect("clicked", lambda _b: self.on_action_save_as(None, None))
        btn_save = Gtk.Button(label="Save")
        btn_save.add_css_class("suggested-action")
        btn_save.connect("clicked", lambda _b: self.on_action_save(None, None))
        btn_close = Gtk.Button(label="Close")
        btn_close.connect("clicked", lambda _b: self.window.close())
        right.append(btn_save_as)
        right.append(btn_save)
        right.append(btn_close)
        box.append(right)
        return box

    # ------------------------------------------------------- field helpers

    def section_label(self, text):
        label = Gtk.Label(label=text, halign=Gtk.Align.START, xalign=0)
        label.add_css_class("panel-label")
        label.set_margin_start(12)
        label.set_margin_top(8)
        return label

    def field_name_label(self, text):
        label = Gtk.Label(label=text, halign=Gtk.Align.END, xalign=1)
        label.add_css_class("field-name")
        return label

    def field_row(self, text, widget):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.append(self.field_name_label(text))
        widget.set_hexpand(True)
        box.append(widget)
        return box

    def make_field_widget(self, key, kind):
        if kind == "enum":
            drop = Gtk.DropDown.new_from_strings(TYPE_CHOICES)
            drop.connect("notify::selected", self.on_enum_changed, key)
            return drop
        if kind == "bool":
            chk = Gtk.CheckButton(label=key)
            chk.set_halign(Gtk.Align.START)
            chk.connect("toggled", self.on_bool_toggled)
            return chk
        entry = Gtk.Entry()
        entry.connect("changed", self.on_entry_changed, key)
        return entry

    # ------------------------------------------------------- list handling

    def filter_func(self, row):
        q = self.search.get_text().strip().lower()
        if not q:
            return True
        item = row.item
        return any(q in item[k].lower() for k in ("name", "summary", "base"))

    def on_search_changed(self, _entry):
        self.listbox.invalidate_filter()

    def refresh(self):
        self.items = [build_item(p) for p in iter_desktop_files()]
        self.items.sort(key=lambda i: i["name"].casefold())
        self.rebuild_list()
        self.count_label.set_text(f"{len(self.items)} applications")

    def rebuild_list(self):
        row = self.listbox.get_first_child()
        while row is not None:
            nxt = row.get_next_sibling()
            self.listbox.remove(row)
            row = nxt
        for item in self.items:
            self.listbox.append(self.make_row(item))

    def make_row(self, item):
        row = AppRow(item)
        return row

    def on_row_selected(self, _listbox, row):
        if self._restoring:
            return
        if row is None:
            self.clear_editor()
            return
        item = row.item
        if (self.current is not None and self.modified
                and str(self.current.path) != item["path"]):
            self.prompt_discard(then=lambda: self.do_load(item),
                                cancel=self.restore_selection)
        else:
            self.do_load(item)

    def restore_selection(self):
        self._restoring = True
        self.listbox.select_row(self._last_row)
        self._restoring = False

    def prompt_discard(self, then, cancel):
        dialog = Gtk.AlertDialog(message="Discard unsaved changes?")
        dialog.set_detail("The current file has uncommitted edits.")
        dialog.set_buttons(["Cancel", "Discard"])
        dialog.set_default_button(0)

        def cb(dlg, result, _user_data):
            if dlg.choose_finish(result) == 1:
                then()
            else:
                cancel()

        dialog.choose(self.window, None, cb, None)

    def select_item_by_path(self, path):
        row = self.listbox.get_first_child()
        while row is not None:
            if row.item["path"] == path:
                self._restoring = True
                self.listbox.select_row(row)
                self.listbox.scroll_to(row, Gtk.ListScrollFlags.NONE, None)
                self._restoring = False
                return
            row = row.get_next_sibling()

    # ------------------------------------------------------------ loading

    def do_load(self, item):
        self._loading = True
        self.current = None
        try:
            entry = DesktopEntry.parse(item["path"])
            self.current = entry
            self.stack.set_visible_child_name("form")
            self.populate_form(entry)
        except Exception as exc:
            self.stack.set_visible_child_name("raw")
            self.raw_path = Path(item["path"])
            self.raw_failure = str(exc)
            try:
                text = Path(item["path"]).read_text(encoding="utf-8",
                                                    errors="replace")
            except OSError:
                text = ""
            self.raw_view.get_buffer().set_text(text)
        self._loading = False
        self.modified = False
        self.window.set_title("Desktop Entry Editor")

        writable = os.access(item["path"], os.W_OK)
        suffix = "" if writable else "  (read-only — use Save As)"
        self.path_label.set_text(item["path"] + suffix)
        self._last_row = self.listbox.get_selected_row()

    def populate_form(self, entry):
        self._bool_touched = set()
        for key, (kind, widget) in self.field_widgets.items():
            value = entry.get(key)
            if kind == "entry":
                widget.set_text(value or "")
            elif kind == "bool":
                widget.set_active(bool_from_str(value))
            elif kind == "enum":
                idx = TYPE_CHOICES.index(value) if value in TYPE_CHOICES else 0
                widget.set_selected(idx)

        self.update_icon(entry.get("Icon") or "")
        self.chk_show_in_menu.set_active(not bool_from_str(entry.get("NoDisplay")))
        self.chk_hidden.set_active(bool_from_str(entry.get("Hidden")))

        self.populate_custom_list(entry)
        self.populate_other_sections(entry)

    def populate_custom_list(self, entry):
        row = self.custom_list.get_first_child()
        while row is not None:
            nxt = row.get_next_sibling()
            self.custom_list.remove(row)
            row = nxt
        standard = {s[0] for s in FIELD_SPECS}
        for key, value in entry.main_options():
            if key in standard or key == "Icon":
                continue
            self.add_custom_row(key, value)

    def add_custom_row(self, key, value):
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                      margin_top=2, margin_bottom=2)
        klabel = Gtk.Label(label=key, xalign=0, halign=Gtk.Align.START,
                           width_chars=24, ellipsize=Pango.EllipsizeMode.END)
        klabel.add_css_class("monospace")
        box.append(klabel)
        entry = Gtk.Entry(text=value or "", hexpand=True)
        entry.connect("changed", self.on_custom_value_changed, key)
        box.append(entry)
        btn = Gtk.Button(icon_name="edit-delete")
        btn.set_tooltip_text(f"Remove {key}")
        btn.connect("clicked", self.on_custom_remove, key)
        box.append(btn)
        row.set_child(box)
        self.custom_list.append(row)

    def populate_other_sections(self, entry):
        lines = []
        for section in entry.other_sections():
            lines.append(f"[{section}]")
            for key, value in entry.parser.items(section):
                lines.append(f"{key} = {value}")
            lines.append("")
        self.other_view.get_buffer().set_text("\n".join(lines))

    def clear_editor(self):
        self.current = None
        self.stack.set_visible_child_name("form")
        self.path_label.set_text("")
        self.window.set_title("Desktop Entry Editor")

    # ------------------------------------------------------------ editing

    def mark_modified(self):
        if self._loading:
            return
        self.modified = True
        self.window.set_title("Desktop Entry Editor *")

    def on_entry_changed(self, entry, key):
        if self._loading or self.current is None:
            return
        text = entry.get_text()
        self.current.set(key, text if text else None)
        self.mark_modified()

    def on_enum_changed(self, dropdown, _pspec, key):
        if self._loading or self.current is None:
            return
        self.current.set(key, TYPE_CHOICES[dropdown.get_selected()])
        self.mark_modified()

    def on_choose_icon(self, _btn):
        if self.current is None:
            return
        picker = IconPickerDialog(
            self.window,
            self.current.get("Icon") or "",
            on_pick=lambda name: self.set_icon(name))
        picker.present()

    def set_icon(self, icon_name):
        if self.current is None:
            return
        self.current.set("Icon", icon_name if icon_name else None)
        self.update_icon(icon_name)
        self.mark_modified()

    def update_icon(self, icon_name):
        icon_name = icon_name or ""
        if icon_name.startswith("/"):
            self.icon_preview.set_from_file(icon_name)
        else:
            self.icon_preview.set_from_icon_name(
                icon_name or "application-x-executable")
        self.icon_name_label.set_text(icon_name or "None")

    def on_bool_toggled(self, chk):
        if self._loading or self.current is None:
            return
        self.mark_modified()
        if chk is self.chk_show_in_menu:
            self.current.set("NoDisplay", "false" if chk.get_active() else "true")
        elif chk is self.chk_hidden:
            self.current.set("Hidden", "true" if chk.get_active() else "false")
        else:
            key = chk.get_label()
            self.current.set(key, "true" if chk.get_active() else "false")

    def on_custom_value_changed(self, entry, key):
        if self._loading or self.current is None:
            return
        text = entry.get_text()
        self.current.set(key, text if text else None)
        if key == "Icon":
            self.update_icon(text)
        self.mark_modified()

    def on_custom_remove(self, _btn, key):
        if self.current is None:
            return
        self.current.set(key, None)
        self.populate_custom_list(self.current)
        self.mark_modified()

    def on_add_key(self, _btn):
        if self.current is None:
            return
        key = self.new_key_entry.get_text().strip()
        if not key or "=" in key or any(c.isspace() for c in key):
            return
        self.current.set(key, "")
        self.populate_custom_list(self.current)
        self.new_key_entry.set_text("")
        self.mark_modified()

    def browse_exec(self, _btn):
        self.pick_file(
            callback=lambda path: self.field_widgets["Exec"][1].set_text(path))

    def browse_path(self, _btn):
        self.pick_folder(
            callback=lambda path: self.field_widgets["Path"][1].set_text(path))

    def pick_file(self, callback):
        dialog = Gtk.FileDialog()
        filt = Gtk.FileFilter()
        filt.set_name("All files")
        filt.add_pattern("*")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(filt)
        dialog.set_filters(store)

        def cb(fd, result, _user_data):
            try:
                gfile = fd.open_finish(result)
            except GLib.Error as exc:
                if exc.matches(Gio.IOErrorEnum, Gio.IOErrorEnum.CANCELLED):
                    return
                self.error(f"Could not pick file: {exc.message}")
                return
            callback(gfile.get_path())

        dialog.open(self.window, None, cb, None)

    def pick_folder(self, callback):
        dialog = Gtk.FileDialog()
        dialog.set_initial_folder(Gio.File.new_for_path(str(Path.home())))

        def cb(fd, result, _user_data):
            try:
                gfile = fd.select_folder_finish(result)
            except GLib.Error as exc:
                if exc.matches(Gio.IOErrorEnum, Gio.IOErrorEnum.CANCELLED):
                    return
                self.error(f"Could not pick folder: {exc.message}")
                return
            callback(gfile.get_path())

        dialog.select_folder(self.window, None, cb, None)

    # -------------------------------------------------------------- saving

    def write_current(self, path):
        path = Path(path)
        if self.stack.get_visible_child_name() == "raw":
            buf = self.raw_view.get_buffer()
            text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            self.raw_path = path
            self.raw_failure = None
        else:
            self.current.save(path)
            self.current = DesktopEntry.parse(path)
        self.modified = False
        self.window.set_title("Desktop Entry Editor")
        self.path_label.set_text(str(path))

    def current_path(self):
        if self.stack.get_visible_child_name() == "raw":
            return getattr(self, "raw_path", None)
        return self.current.path if self.current else None

    def on_action_save(self, _a, _p):
        path = self.current_path()
        if path is None:
            return
        try:
            self.write_current(path)
        except (OSError, configparser.Error) as exc:
            self.error(f"Could not save:\n{exc}\n\n"
                       "Use “Save As…” if the file is read-only.")

    def on_action_save_as(self, _a, _p):
        path = self.current_path()
        if path is None:
            return
        dialog = Gtk.FileDialog()
        dialog.set_initial_folder(Gio.File.new_for_path(str(USER_APPS_DIR)))
        dialog.set_initial_name(Path(path).name)

        def cb(fd, result, _user_data):
            try:
                gfile = fd.save_finish(result)
            except GLib.Error as exc:
                if exc.matches(Gio.IOErrorEnum, Gio.IOErrorEnum.CANCELLED):
                    return
                self.error(f"Could not pick location: {exc.message}")
                return
            path = gfile.get_path()
            try:
                self.write_current(path)
            except (OSError, configparser.Error) as exc:
                self.error(f"Could not save:\n{exc}")
                return
            self.refresh()
            self.select_item_by_path(path)

        dialog.save(self.window, None, cb, None)

    def on_action_new(self, _a, _p):
        if self.current_path() is not None and self.modified:
            self.prompt_discard(then=self.show_new_dialog,
                                cancel=lambda: None)
        else:
            self.show_new_dialog()

    def show_new_dialog(self):
        dialog = Gtk.Window(title="New desktop entry",
                            transient_for=self.window, modal=True,
                            resizable=False)
        dialog.add_css_class("icon-picker")
        dialog.set_default_size(420, -1)

        name_entry = Gtk.Entry(placeholder_text="Application name")
        file_entry = Gtk.Entry(placeholder_text="File name (e.g. MyApp.desktop)")
        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        form.append(Gtk.Label(label="Name", halign=Gtk.Align.START))
        form.append(name_entry)
        form.append(Gtk.Label(label="File name", halign=Gtk.Align.START))
        form.append(file_entry)
        form.set_hexpand(True)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _b: dialog.close())
        create_btn = Gtk.Button(label="Create")
        create_btn.add_css_class("suggested-action")
        create_btn.connect("clicked", lambda _b: create())
        name_entry.connect("activate", lambda _e: create())
        file_entry.connect("activate", lambda _e: create())
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                         halign=Gtk.Align.END)
        bottom.append(cancel_btn)
        bottom.append(create_btn)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                       margin_top=12, margin_bottom=12, margin_start=12,
                       margin_end=12)
        root.append(form)
        root.append(bottom)
        dialog.set_child(root)
        name_entry.grab_focus()
        dialog.present()

        def create():
            name = name_entry.get_text().strip()
            fname = file_entry.get_text().strip() or name
            if not fname.endswith(".desktop"):
                fname += ".desktop"
            fname = "".join(c for c in fname if c not in "/\\")
            if not fname:
                dialog.close()
                return
            target = USER_APPS_DIR / fname
            if target.exists():
                self.error(f"{target} already exists. Choose another file name.")
                return
            entry = DesktopEntry(target)
            entry.set("Type", "Application")
            entry.set("Name", name or Path(fname).stem)
            try:
                entry.save()
            except OSError as exc:
                self.error(f"Could not create file:\n{exc}")
                dialog.close()
                return
            dialog.close()
            self.refresh()
            self.select_item_by_path(str(target))

    def on_action_delete(self, _a, _p):
        path = self.current_path()
        if path is None:
            return
        path = Path(path)
        dialog = Gtk.AlertDialog(message="Delete this entry?")
        dialog.set_detail(str(path))
        dialog.set_buttons(["Cancel", "Delete"])
        dialog.set_default_button(0)

        def cb(dlg, result, _user_data):
            if dlg.choose_finish(result) != 1:
                return
            try:
                path.unlink()
            except OSError as exc:
                self.error(f"Could not delete:\n{exc}")
                return
            self.current = None
            self.modified = False
            self.clear_editor()
            self.refresh()

        dialog.choose(self.window, None, cb, None)

    def on_action_refresh(self, _a, _p):
        self.refresh()

    def on_action_quit(self, _a, _p):
        self.quit()

    def on_action_about(self, _a, _p):
        dialog = Gtk.AlertDialog(message="Desktop Entry Editor")
        dialog.set_detail(
            "A GTK4 editor for .desktop files,\n"
            "styled after KDE's KMenuEdit.\n\n"
            "Files are read from ~/.local/share/applications,\n"
            "/usr/local/share/applications and /usr/share/applications.\n\n"
            "Comments inside .desktop files are not preserved on save.")
        dialog.set_buttons(["Close"])
        dialog.set_default_button(0)
        dialog.choose(self.window, None, lambda d, r, _ud: None, None)

    def error(self, message):
        dialog = Gtk.AlertDialog(message="Error")
        dialog.set_detail(message)
        dialog.set_buttons(["OK"])
        dialog.set_default_button(0)
        dialog.choose(self.window, None, lambda d, r, _ud: None, None)


def main():
    app = App()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
