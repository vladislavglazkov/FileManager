from collections.abc import Hashable
from typing import Iterable, Mapping
from typing import Callable
import typing
from typing import Dict
from typing_extensions import Literal
import urwid
import asyncio
import time
import os
from cli.dispatchdoubleclick import DispatchDoubleClick
from cli.error import ErrorWindow
from cli.manager import Manager
from cli.props import PropertyWindow, PropertyWindowMock
from logic.file import File
from logic.workspace import Workspace
from logic.configmanager import ConfigManager
from logic.workspacemanager import WorkspaceManager


class TableEntry(urwid.Widget):
    def rows(self, size: tuple[int], focus: bool = False) -> int:
        return 1
    _selectable = True

    def __init__(self, data) -> None:
        super().__init__()
        self.data = data
        self._column_content = []
        ops = self.data
        init_list = []
        for h in self.__class__.schema:
            method = h["method"]
            sz = h['size']
            method_type = h["type"]

            if (method_type == 'text'):
                value = method(self)
                text = urwid.Text(value, wrap='ellipsis')
                self._column_content.append(text)
            elif (method_type == 'widget'):
                self._column_content.append(
                    method(self))
            init_list.append(('weight', sz, self._column_content[-1]))

        self._columns = urwid.Columns(init_list)
        self._columns = urwid.AttrMap(self._columns, "normal", "reversed")

    def reload_data(self):
        i = 0
        ops = self.data
        for h in self.__class__.schema:
            method = h["method"]
            method_type = h["type"]
            if (method_type == 'text'):
                self._column_content[i].set_text(
                    method(self))
            elif (method_type == 'widget'):
                self._column_content[i].update_data()
            i += 1

    def render(self, size: tuple[int], focus: bool = False) -> urwid.Canvas:
        (maxcol,) = size
        self.reload_data()
        return self._columns.render(size, focus)


class Selectable(urwid.Text):
    mapping = {False: "( )",
               True: "(*)",
               "unavailable": "(x)"}

    def __init__(self, custom_data: dict) -> None:
        self._custom_data = custom_data.copy()
        super().__init__(
            Selectable.mapping[self._custom_data["FileEntry"].is_selected()], align='center')

    _selectable = True

    def update_data(self):
        super().set_text(
            Selectable.mapping[self._custom_data["FileEntry"].is_selected()])

    def mouse_event(self, size: tuple[()] | tuple[int] | tuple[int, int],
                    event: str, button: int, col: int, row: int, focus: bool) -> bool | None:
        if button == 1 and event == 'mouse press':
            self._custom_data["FileEntry"].revert_selection()

    def selectable(self) -> bool:
        return True

    def render(self, size: tuple[int] | tuple[()],
               focus: bool = False) -> urwid.TextCanvas:
        return super().render(size, focus)


class FileName(urwid.Widget):
    def rows(self, size, focus):
        return 1

    def get_normal(self) -> str:
        return self._custom_data["FileEntry"].get_color()

    def get_focused(self) -> str:
        return "rev " + self.get_normal()

    def __init__(self, custom_data: dict) -> None:
        super().__init__()
        self._custom_data = custom_data.copy()
        self._text = urwid.Text(
            self._custom_data["FileEntry"].data.get_name_formatted(), wrap='ellipsis')

    def update_data(self):
        self._text = urwid.Text(
            self._custom_data["FileEntry"].data.get_name_formatted(), wrap='ellipsis')

    _selectable: False

    def selectable(self) -> bool:
        return False

    def render(self, size: tuple[int] | tuple[()],
               focus: bool = False) -> urwid.TextCanvas:
        mp = urwid.AttrMap(self._text, {None: (self.get_focused(
        ) if self._custom_data["FileEntry"].focused else self.get_normal())})
        return mp.render(size, focus)


class Title(urwid.AttrMap, DispatchDoubleClick):
    def selectable(self) -> bool:
        return True

    def get_state(self) -> None | Literal["asc", "desc"]:
        prop, sort_type = self._custom_data["FilePanel"].get_sort()
        if prop == self._prop:
            return sort_type
        return None

    def update(self) -> None:
        self._text.set_text(self.get_text())
        self._invalidate()

    def cancel_state(self) -> None:
        self._state = None
        self._invalidate()

    def get_text(self) -> str:
        temp = self._name
        if self.get_state() == "asc":
            temp += " ↑"
        if self.get_state() == "desc":
            temp += " ↓"
        return temp

    def next_state(self) -> None:
        ctype = self.get_state()

        self._custom_data["Workspace"].set_sort(
            self._prop, "asc" if ctype != "asc" else "desc")

    def keypress(self, size: tuple[()] | tuple[int]
                 | tuple[int, int], key: str) -> str | None:
        if key == Manager.KeyMap.toggle():
            self.next_state()
        return super().keypress(size, key)

    def double_click(self):
        self.next_state()

    def mouse_event(self, size: tuple[()] | tuple[int] | tuple[int, int],
                    event: str, button: int, col: int, row: int, focus: bool) -> bool | None:
        if event == "mouse press" and button == 1:
            self.dispatch_double_click()
        return super().mouse_event(size, event, button, col, row, focus)

    def __init__(self, custom_data, name: str, property: str,
                 callback: Callable) -> None:
        self._custom_data = custom_data.copy()
        self._name = name
        self._prop = property
        self._state: Literal["asc", "desc"] | None = None
        self._last_click = 0
        self._text = urwid.Text(self.get_text())
        super().__init__(self._text, "default", "reversed")


class FileEntry(TableEntry, DispatchDoubleClick):
    def __init__(self, custom_data, data: File, pos: int,
                 workspace: Workspace) -> None:
        data.subscribe(self.rebuild)
        self._custom_data = custom_data.copy()
        self.pos = pos
        self._workspace = workspace
        self._custom_data["FileEntry"] = self
        self.focused = False
        super().__init__(data)

    def is_selected(self) -> bool | Literal["unavailable"]:
        return self.data.getSelected()

    def get_selectable(self) -> Selectable:
        return Selectable(self._custom_data)

    def get_file_name(self) -> FileName:
        return FileName(self._custom_data)

    def get_formatted_size(self):
        return self.data.getFormattedSize()

    def get_modified_formatted(self):
        return self.data.get_modified_formatted()
    schema = [
        {'method': get_file_name,
         'size': 3,
         'type': 'widget'},
        {'method': get_formatted_size,
         'size': 1,
         'type': 'text'},
        {'method': get_modified_formatted,
         'size': 1,
         'type': 'text'},
        {'method': get_selectable,
         'size': 0.5,
         'type': 'widget'}
    ]

    title_schema = [
        {"name": "name",
         "field": "name"},
        {"name": "size",
         "field": "size"},
        {"name": "last modified",
         "field": "modified"},
        None
    ]

    def revert_selection(self) -> None:
        if self.data.getSelected() == 'unavailable':
            return
        self._workspace.set_selected(self.data, not self.data.getSelected())

    def double_click(self) -> None:
        self.step_in()

    def rebuild(self) -> None:
        self._invalidate()

    def mouse_event(self, size: tuple[int], event: str, button: int,
                    col: int, row: int, focus: bool) -> bool | None:
        if event == "mouse press" and button == 1:
            self.dispatch_double_click()

        return self._columns.mouse_event(size, event, button, col, row, focus)

    def get_color(self) -> str:
        if self.data.isDir():
            return "folds"
        if self.data.is_executable():
            return "execs"
        return "normal"

    def step_in(self) -> None:

        if self.data.isDir():
            # content.update(self.data.getPath(),self.pos)
            res = self._workspace.step_in(self.data.getPath())
            if res is not None:
                self._custom_data["TwoTabs"].push_on_stack(ErrorWindow(res))
        else:
            command = ConfigManager.get_command(self.data.getPath())
            if command is not None:
                os.system(command)
                WorkspaceManager.rebuild_all()
                Manager.global_redraw()

    def keypress(self, size: tuple[()] | tuple[int]
                 | tuple[int, int], key: str) -> str | None:
        super().keypress(size, key)
        if key == Manager.KeyMap.enter():
            self.step_in()
        if key == Manager.KeyMap.props() and Manager.get_lock() is None:
            pw = PropertyWindow(self.data)
            self._custom_data["viewstack_push_function"](pw)
        if key == Manager.KeyMap().toggle() and Manager.get_lock() is None:
            self.revert_selection()
            # self._invalidate()
        return super().keypress(size, key)

    def render(self, size: tuple[int], focus: bool = False) -> urwid.Canvas:
        inv = False
        if self.focused != focus:
            inv = True
        self.focused = focus
        if inv:
            for h in self._column_content:
                h._invalidate()
        return super().render(size, focus)


class TitleEntry(urwid.Pile):

    def __init__(self, custom_data):
        self._custom_data = custom_data.copy()
        arr = []
        for i in range(len(FileEntry.schema)):
            if FileEntry.title_schema[i] is None:
                arr.append(
                    ('weight', FileEntry.schema[i]["size"], urwid.Text("")))
            else:
                # pass
                arr.append(('weight', FileEntry.schema[i]["size"], Title(
                    self._custom_data, FileEntry.title_schema[i]["name"], FileEntry.title_schema[i]["field"], None)))

        super().__init__(
            [urwid.Columns(arr, dividechars=1), urwid.Divider("-")])


class PanelPathPart(urwid.Text, DispatchDoubleClick):
    def selectable(self) -> bool:
        return True

    def __init__(self, custom_data: dict, path: str) -> None:
        self._path = path
        self._custom_data = custom_data.copy()
        super().__init__(path.split('/')[-1])

    def move(self):
        res = self._custom_data["Workspace"].step_in(self._path)
        if res is not None:
            self._custom_data["TwoTabs"].push_on_stack(ErrorWindow(res))

    def double_click(self):
        self.move()

    def mouse_event(self, size: tuple[()] | tuple[int] | tuple[int, int],
                    event: str, button: int, col: int, row: int, focus: bool) -> bool | None:
        if event == "mouse press" and button == 1:
            self.dispatch_double_click()

        return super().mouse_event(size, event, button, col, row, focus)

    def keypress(self, size: tuple[()] | tuple[int]
                 | tuple[int, int], key: str) -> str | None:
        if key == Manager.KeyMap.enter():
            self.move()
            return None
        return super().keypress(size, key)


class PanelPath(urwid.Pile):
    def __init__(self, custom_data):

        paths = custom_data["Workspace"].get_path().split('/')
        objs = [urwid.Text("/")]
        for i in range(2, len(paths) + 1):
            temp = "/" + "/".join(paths[1:i])
            objs.append(urwid.AttrMap(PanelPathPart(
                custom_data, temp), "normal", "reversed"))
            objs.append(urwid.Text("/"))

        super().__init__([urwid.Columns([('pack', h)
                                         for h in objs], dividechars=0)] + [urwid.Divider("-")])
