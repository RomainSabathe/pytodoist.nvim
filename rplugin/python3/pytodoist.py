import subprocess
from abc import abstractmethod
import os
import re
from pathlib import Path
from typing import List, Optional, Union
from copy import copy, deepcopy
from dataclasses import dataclass

import pynvim
import todoist

NULL = "null"
SMART_TAG = True


@pynvim.plugin
class Plugin(object):
    def __init__(self, nvim):
        self.nvim = nvim
        if not os.environ.get("TODOIST_API_KEY"):
            raise ValueError("Can't find the TODOIST_API_KEY env var.")
        self.todoist = TodoistInterface(
            todoist.TodoistAPI(os.environ.get("TODOIST_API_KEY"))
        )
        self.parsed_buffer_since_last_save = None
        self.parsed_buffer = None

    def _get_buffer_content(self) -> List[str]:
        return self.nvim.current.buffer[:]

    @pynvim.autocmd("InsertEnter", pattern=".todoist", sync=False)
    def register_current_line(self):
        pass

    @pynvim.autocmd("CursorMoved", pattern=".todoist", sync=False)
    def cursor_moved(self):
        self.parsed_buffer = ParsedBuffer(self._get_buffer_content(), self.todoist)
        self._refresh_highlights()

    @pynvim.autocmd("BufWritePre", pattern=".todoist", sync=True)
    def save_buffer(self):
        if self.parsed_buffer_since_last_save is None:
            # This is triggered at the first initialization of `_load_tasks`.
            # If we don't return early, we'd be stuck in an endless loop of syncing
            # and saving.
            return

        updated_buffer = ParsedBuffer(self._get_buffer_content())
        self.parsed_buffer_since_last_save.compare_with(updated_buffer)
        self.todoist.commit()
        self.todoist.sync()
        self.parsed_buffer_since_last_save = ParsedBuffer(
            self._get_buffer_content(), self.todoist
        )
        self.parsed_buffer = ParsedBuffer(self._get_buffer_content(), self.todoist)
        self._setup_highlight_groups()
        self._refresh_highlights()
        # self.load_tasks(None)

    @pynvim.autocmd("InsertLeave", pattern=".todoist", sync=True)
    def register_updated_line(self):
        pass

    def _input_project_from_fzf(self) -> str:
        projects = [project.name for project in self.todoist.projects]

        # This command instantiates a global vimscript variable named `fzf_output`.
        self.nvim.api.command("call ResetFzfOutput()")
        self.nvim.api.command(
            "call fzf#run({"
            "'sink': function('CaptureFzfOutput'),"
            f"'source': {projects}"
            "})"
        )
        # However fzf#run returns directly (it doesn't wait for the user to complete
        # its input).
        # So we hack together a wait to constantly check if the user has finished.
        fzf_output = None
        while fzf_output is None:
            try:
                fzf_output = self.nvim.api.eval("fzf_output")
            except:
                pass

        return fzf_output

    @pynvim.function("MoveTask", sync=False, range=True)
    def move_task(self, args, _range):
        self.nvim.api.command("set modifiable")
        project_name = self._input_project_from_fzf()
        if project_name == "":
            return

        self.nvim.api.command("let position = getcurpos()")
        buf_index, line_index, col_index, offset, _ = self.nvim.api.eval("position")

        project = self.todoist.get_project_by_name(project_name)

        # # TODO: still unsure if we want to do this...
        # # item = self.parsed_buffer[line_index - 1]
        # # item.move(project_id=project.id)

        # Finding where to paste the tasks.
        for i, item in enumerate(self.parsed_buffer):
            if isinstance(item, Project) and item.id == project.id:
                # We found the project in which to place the task. We could place the
                # task right here. However we choose to place the task at the bottom of
                # the task list by default.
                # We need to iterate one last time to find it.
                break
        for j, item in enumerate(self.parsed_buffer[i:]):
            if isinstance(item, ProjectSeparator):
                # We finally found where to place the task.
                break

        # We need to paste the line(s) at position `i + j - 1`.
        # For each line, we delete and paste.
        # We execute whatever is closest to the end of the file first, to preserve
        # line ordering.
        # TODO: something is still off.
        self.nvim.api.command(f"{_range[0]},{_range[1]}d")
        self.nvim.api.command(f"{i+j-1}pu")
        self.nvim.api.command(
            f"call setpos('.', [{buf_index}, {line_index}, {col_index}, {offset}])"
        )

    @pynvim.function("TodoistCleanup", sync=True)
    def todoist_cleanup(self, args):
        """Delete the tasks that are empty."""
        # TODO: redistribute the child-orders if there are clashes.
        for task in self.todoist.tasks:
            if task.content == "":
                task.delete()
        self.todoist.commit()
        self.load_tasks([])

    @pynvim.function("LoadTasks", sync=True)
    def load_tasks(self, args):
        self._clear_buffer()
        self.todoist.sync()
        for i, item in enumerate(self.todoist):
            item = str(item)
            if i == 0:
                self.nvim.current.line = item
            else:
                self.nvim.current.buffer.append(item)

        # Cancel the "modified" state of the buffer.
        self.nvim.api.command("w!")
        self.parsed_buffer_since_last_save = ParsedBuffer(
            self._get_buffer_content(), self.todoist
        )
        self.parsed_buffer = ParsedBuffer(self._get_buffer_content(), self.todoist)
        self._setup_highlight_groups()
        self._refresh_highlights()

    def _clear_buffer(self):
        # TODO: write this in vimscript.
        # If there is a buffer with name 'todoist', we must close it first.
        for buffer in self.nvim.api.list_bufs():
            filepath = Path(buffer.api.get_name())
            if filepath.name == ".todoist":
                # We found a 'todoist' buffer. We delete it.
                self.nvim.command(f"bdelete! {buffer.number}")
                break
        self.nvim.api.command("enew")
        self.nvim.api.command("set filetype=todoist")
        self.nvim.api.command("file .todoist")  # Set the filename.

    def _get_current_line_index(self):
        return self.nvim.eval("line('.')")

    def _get_number_of_lines(self):
        return self.nvim.current.buffer.api.line_count()

    def _setup_highlight_groups(self):
        for i, item in enumerate(self.parsed_buffer):
            if isinstance(item, Project):
                # Setting up color for the project's name itself
                # TODO: have a function returning this group_name. The naming logic
                # should be centralized.
                group_name = f"Project{sanitize_str(item.name)}"
                self.nvim.api.command(
                    f"highlight {group_name} "
                    f"cterm=bold gui=bold "
                    f"guifg={item.rgbcolor}"
                )
                # Setting up color for the project's tasks
                group_name = f"Tasks{sanitize_str(item.name)}"
                self.nvim.api.command(
                    f"highlight {group_name} "
                    f"gui=NONE "
                    f"guifg={item.rgbcolor}"
                )

    def _refresh_highlights(self):
        highlight_group, highlight_group_suffix = None, None
        for i, item in enumerate(self.parsed_buffer):
            # We read the buffer from top to bottom. Every time we encounter a project,
            # all subsequent items get assigned to its color. Until we find another
            # project.
            if isinstance(item, Project):
                highlight_group_suffix = sanitize_str(item.name)

            if isinstance(item, (Project, ProjectUnderline)):
                highlight_group = f"Project{highlight_group_suffix}"
            else:
                highlight_group = f"Tasks{highlight_group_suffix}"
            self.nvim.current.buffer.add_highlight(highlight_group, i, 0, -1)

    def echo(self, message: str):
        # Type `:help nvim_echo` for more info about the args.
        self.nvim.api.echo([[str(message), ""]], True, {})


class TodoistInterface:
    def __init__(self, todoist_api: todoist.api.TodoistAPI):
        self.api = todoist_api
        self.tasks = None
        self.projects = None

    def sync(self):
        self.api.sync()
        self.tasks = [Task(data=item) for item in self.api.state["items"]]
        self.projects = [Project(data=item) for item in self.api.state["projects"]]

    def get_project_by_name(self, project_name):
        for project in self.projects:
            if project_name.lower() == project.name.lower():
                return project
        return None

    def get_task_by_content(self, content):
        for task in self.tasks:
            if content == task.content:
                return task
        return None

    def __iter__(self):
        for project in self.projects:
            if not project.isvalid():
                continue
            yield project
            yield ProjectUnderline(project_name=project.name)
            for task in sorted(self.tasks, key=lambda task: task.child_order):
                if task.isin(project) and task.isvalid():
                    yield task
            yield ProjectSeparator()

    def add_task(self, *args, **kwargs):
        # We populate this fields because the `isvalid` function will use it.
        if "is_deleted" not in kwargs.keys():
            kwargs["is_deleted"] = False
        if "in_history" not in kwargs.keys():
            kwargs["in_history"] = False
        if "date_completed" not in kwargs.keys():
            kwargs["date_completed"] = None
        if "child_order" not in kwargs.keys():
            kwargs["child_order"] = 99  # TODO: dirty.
        return self.api.items.add(*args, **kwargs)

    def commit(self):
        return self.api.commit()


class Project:
    def __init__(self, name: str = None, data: todoist.models.Project = None):
        assert name is not None or data is not None
        self.name = name
        self.data = data

        if data is not None and name is None:
            self.name: str = data["name"]

    @property
    def id(self):
        if self.data is not None:
            return self.data["id"]
        return "[Not synced]"

    @property
    def rgbcolor(self):
        if self.data is not None:
            return BG_COLORS_ID_TO_HEX[self.data["color"]]
        return "#ffffff"

    def __str__(self):
        return self.name

    def __repr__(self) -> str:
        return f"Project #{self.id}: {self.name}"

    def __hash__(self):
        if self.id != "Not synced":
            return hash(self.id)
        return hash(self.__repr__())

    def __eq__(self, rhs):
        if self.id != "[Not synced]" and rhs.id != "[Not synced]":
            return self.id == rhs.id
        return self.__repr__() == rhs.__repr__()

    def update(self, *args, **kwargs):
        to_return = self.data.update(*args, **kwargs)
        if "name" in kwargs.keys():
            self.name = kwargs["name"]
        return to_return

    def isvalid(self):
        if self.data is None:
            return True
        return not (self.data["is_archived"] or self.data["is_deleted"])


class Task:
    def __init__(self, content: str = None, data: todoist.models.Item = None):
        assert content is not None or data is not None
        self.content = content
        self.data = data
        self.depth = 0

        if data is not None and content is None:
            self.content = data["content"]

    @property
    def id(self):
        if self.data is not None:
            return self.data["id"]
        return "[Not synced]"

    @property
    def child_order(self):
        if self.data is not None:
            return self.data["child_order"]
        return 1

    def __repr__(self) -> str:
        short_content = (
            self.content if len(self.content) < 50 else f"{self.content[:47]}..."
        )
        return f"Task #{self.id}: {short_content}"

    def __str__(self):
        buffer = ""
        for _ in range(self.depth):
            buffer += "    "
        buffer += self.content
        return buffer

    def __hash__(self):
        if self.id != "Not synced":
            return hash(self.id)
        return hash(self.__repr__())

    def __eq__(self, rhs):
        if self.id != "[Not synced]" and rhs.id != "[Not synced]":
            return self.id == rhs.id
        return self.__repr__() == rhs.__repr__()

    def isin(self, project: Project):
        if self.data is None or project.data is None:
            return False
        return self.data["project_id"] == project.id

    def isvalid(self):
        if self.data is None:
            return True
        return not (
            self.data["is_deleted"]
            or self.data["in_history"]
            or self.data["date_completed"] is not None
        )

    def update(self, *args, **kwargs):
        to_return = self.data.update(*args, **kwargs)
        if "content" in kwargs.keys():
            self.content = kwargs["content"]
        return to_return

    def delete(self):
        self.data.delete()
        self.content = "[Deleted]"

    def move(self, *args, **kwargs):
        return self.data.move(*args, **kwargs)


class ProjectUnderline:
    def __init__(self, project_name: str):
        self.project_name = project_name

    def __repr__(self):
        return "ProjectUnderline"

    def __str__(self):
        return "=" * len(self.project_name)


class ProjectSeparator:
    def __init__(self):
        pass

    def __repr__(self):
        return "ProjectSeparator"

    def __str__(self):
        return ""


class ParsedBuffer:
    def __init__(self, lines: List[str], todoist: TodoistInterface = None):
        self._raw_lines = lines
        self.todoist = todoist

        self.items = self.parse_lines()
        if self.todoist is not None:
            self.fill_items_with_data()

    # TODO: this function is not stateful.
    def parse_lines(self):
        items = []

        k = 0
        while k < len(self._raw_lines):
            line = self._raw_lines[k]

            # Look ahead: checking if the current line is actually a project.
            potential_project_name = line
            potential_underline = ProjectUnderline(potential_project_name)
            if (
                potential_project_name != ""
                and k + 1 < len(self._raw_lines)
                and str(potential_underline) == self._raw_lines[k + 1]
            ):
                # We are indeed scanning a project name. We register this info
                # and move on.
                items.append(Project(name=potential_project_name))
                items.append(potential_underline)
                k += 2
                continue

            # The remaining possibilities are: a proper task or a ProjectSeparator.
            item = Task(content=line) if line != "" else ProjectSeparator()
            items.append(item)
            k += 1
        return items

    def fill_items_with_data(self):
        for i, item in enumerate(self.items):
            if isinstance(item, Project):
                project = self.todoist.get_project_by_name(item.name)
                if project is not None:
                    self.items[i] = project
            elif isinstance(item, Task):
                task = self.todoist.get_task_by_content(item.content)
                if task is not None:
                    self.items[i] = task

    def __iter__(self):
        yield from self.items

    def __getitem__(self, i):
        return self.items[i]

    def _get_project_at_line(self, i: int) -> Project:
        # We take the first project that we encounter by "moving up" in the document.
        for item in self[:i][::-1]:
            if isinstance(item, Project):
                return item
        raise Exception("Couldn't find project.")

    # TODO: I have to find another name for this.
    # Also: there is a big assumption: `self` should be synced with Todoist (all ids
    # are available) whereas `other` might not be.
    def compare_with(self, other):
        diff = Diff(self, other)

        print("\n".join(diff.raw_diff))

        for diff_segment in diff:
            # We apply `-1` because the indices returned by the Diff engine are relative
            # to a text buffer which starts indexing at 1.
            # The ParsedBuffer, however, starts indexing at 0.
            from_index = diff_segment.from_index - 1
            to_index = diff_segment.to_index - 1
            modification_span = max(to_index - from_index, len(diff_segment))

            # A diff segment is composed of 3 things:
            # 1. The type of action (change, add, delete).
            # 2. The indices of lines that are involved.
            # 3. The actual modified lines.
            # Sometimes, items 2. and 3. don't match, and we have a larger span than
            # there are of "modified lines" or vice-versa.
            # To easy the comparison, we make sure that they match, by filling with
            # potential None values.
            befores = self[from_index:to_index]
            befores.extend([None for _ in range(len(befores), modification_span)])

            afters = diff_segment.modified_lines
            afters.extend([None for _ in range(len(afters), modification_span)])

            for i, (item_before, item_after) in enumerate(zip(befores, afters)):
                if item_before is None or diff_segment.action_type == "a":
                    project = self._get_project_at_line(from_index + i)
                    self.todoist.add_task(content=item_after, project_id=project.id)
                elif item_after is None or diff_segment.action_type == "d":
                    if isinstance(item_before, Task):
                        item_before.delete()
                else:
                    if isinstance(item_before, Task):
                        item_before.update(content=item_after)
                    elif isinstance(item_before, Project):
                        item_before.update(name=item_after)


BG_COLORS_ID_TO_HEX = {
    30: "#b8256f",
    31: "#db4035",
    32: "#ff9933",
    33: "#fad000",
    34: "#afb83b",
    35: "#7ecc49",
    36: "#299438",
    37: "#6accbc",
    38: "#158fad",
    39: "#14aaf5",
    40: "#96c3eb",
    41: "#4073ff",
    42: "#884dff",
    43: "#af38eb",
    44: "#eb96eb",
    45: "#e05194",
    46: "#ff8d85",
    47: "#808080",
    48: "#b8b8b8",
    49: "#ccac93",
}

TodoistObjects = Union[Task, Project, ProjectUnderline, ProjectSeparator]


class Diff:
    def __init__(
        self,
        lhs: List[Union[str, TodoistObjects, ParsedBuffer]],
        rhs: List[Union[str, TodoistObjects, ParsedBuffer]],
    ):
        self.lhs = "\n".join([str(item) for item in lhs])
        self.rhs = "\n".join([str(item) for item in rhs])

        self.raw_diff = self.get_raw_diff(self.lhs, self.rhs)

    def __iter__(self):
        if self.raw_diff == [""]:
            # Case where there are no differences.
            return

        # We build a regex capable of registering all possible commands from `ed`
        # (as given by `diff`).
        # Some examples: 90a - 62,67d - 150,160c
        reg = re.compile(
            f"^(?P<from_index>\d+)(,(?P<to_index>\d+))?(?P<action_type>a|c|d)$"
        )

        k = 0
        lines = self.raw_diff  # Shorter name for readibility.
        while k < len(lines):
            matches = reg.match(lines[k])

            if matches.group("action_type") in ["a", "c"]:
                modified_lines = []
                while lines[k] != ".":
                    k += 1
                    modified_lines.append(lines[k])
                modified_lines = modified_lines[:-1]  # Deleting the last "."
                yield DiffSegment(
                    matches.group("action_type"),
                    matches.group("from_index"),
                    matches.group("to_index"),
                    modified_lines,
                )

            elif matches.group("action_type") == "d":
                yield DiffSegment(
                    matches.group("action_type"),
                    matches.group("from_index"),
                    matches.group("to_index"),
                    [],
                )

            k += 1

    @abstractmethod
    def get_raw_diff(self, lhs: str, rhs: str):
        # TODO: that's dirty. Ideally we should pipe directly to `diff`.
        path_lhs = Path("/tmp/lhs")
        if path_lhs.exists():
            path_lhs.unlink()
        path_lhs.write_text(lhs)

        path_rhs = Path("/tmp/rhs")
        if path_rhs.exists():
            path_rhs.unlink()
        path_rhs.write_text(rhs)

        diff_output = subprocess.run(
            ["diff", "-e", str(path_lhs), str(path_rhs)], capture_output=True
        )
        # Trimming the last "\n"
        diff_output = diff_output.stdout.decode()[:-1]

        return diff_output.split("\n")


@dataclass
class DiffSegment:
    action_type: str
    from_index: Union[str, int]
    to_index: Optional[Union[str, int]]
    modified_lines: List[str]

    def __post_init__(self):
        self.from_index: int = int(self.from_index)
        if self.to_index is not None:
            self.to_index: int = int(self.to_index) + 1
        else:
            self.to_index: int = self.from_index + 1

    def __getitem__(self, i: int):
        try:
            return self.modified_lines[i]
        except:
            import ipdb

            ipdb.set_trace()
            pass

    def __len__(self):
        return len(self.modified_lines)

    def __iter__(self):
        yield from self.modified_lines


def sanitize_str(s):
    # fmt: off
    special_chars = [
        " ", "-", ".", "&", "%", "$", "#", "@", "?", "!", "^", "*", "(", ")", "_",
        "+", "=", "`", "~", r"\\", r"|"
    ]
    # fmt: on
    for char in special_chars:
        s = s.replace(char, "")
    return s
