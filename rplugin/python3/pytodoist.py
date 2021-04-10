import os
import re
from pathlib import Path
from typing import List
from copy import copy, deepcopy
from dataclasses import dataclass

import neovim
import todoist

# from .utils import AddDiff, get_diffs

NULL = "null"
SMART_TAG = True

import re
import subprocess
from pathlib import Path


@neovim.plugin
class Plugin(object):
    def __init__(self, nvim):
        self.nvim = nvim
        if not os.environ.get("TODOIST_API_KEY"):
            raise ValueError("Can't find the TODOIST_API_KEY env var.")
        self.todoist = todoist.TodoistAPI(os.environ.get("TODOIST_API_KEY"))
        self.todoist.sync()

    def _get_buffer_content(self) -> List[str]:
        return self.nvim.current.buffer[:]

    @neovim.autocmd("InsertEnter", pattern="todoist", sync=False)
    def register_current_line(self):
        line = self.nvim.current.line.strip()
        self.current_task = self.tasks[line] if line else None

        self.last_buffer = copy(self._get_buffer_content())

    @neovim.autocmd("CursorMoved", pattern="todoist", sync=True)
    def cursor_moved(self):
        if self.last_buffer is None:
            self.last_buffer = copy(self._get_buffer_content())
        # self.nvim.command(f"echom 'hello'")
        self.register_updated_line()

    @neovim.autocmd("InsertLeave", pattern="todoist", sync=True)
    def register_updated_line(self):
        new_buffer = copy(self._get_buffer_content())
        diffs = get_diffs(self.last_buffer, new_buffer)
        for diff in diffs:
            if isinstance(diff, AddDiff):
                index = diff.index - 1
                associated_project = self.world.line_to_project(index)
                for line in diff.new_lines:
                    self._create_task(line, project=associated_project)
            elif isinstance(diff, ChangeDiff):
                index = diff.index - 1
                new_line = diff.new_lines[0]
                item = self.world[index]
                if isinstance(item, TaskInfo):
                    self.todoist.items.update(item.id, content=new_line)
                elif isinstance(item, (ProjectSeparator, ProjectUnderline)):
                    associated_project = self.world.line_to_project(index)
                    self._create_task(new_line, project=associated_project)
            elif isinstance(diff, DeleteDiff):
                for index in diff.index_range:
                    index = index - 1
                    item = self.world[index]
                    self.nvim.command(f"""echom 'Will be deleted: {str(item)}'""")
                    if isinstance(item, TaskInfo):
                        self.todoist.items.delete(item.id)
                    elif isinstance(item, (ProjectSeparator, ProjectUnderline)):
                        pass
                    elif isinstance(item, Project):
                        pass

        if len(diffs) > 0:
            self.todoist.commit()
            self.world = World(self.todoist)
            self.last_buffer = new_buffer

    @neovim.function("LoadTasks", sync=True)
    def load_tasks(self, args):
        self.parsed_buffer = ParsedBuffer(self.todoist)
        for i, line in enumerate(self.world.iterstr()):
            if i == 0:
                self.nvim.current.line = line
            else:
                self.nvim.current.buffer.append(line)

        self._refresh_colors()

    def _clear_buffer(self):
        # If there is a buffer with name 'todoist', we must close it first.
        for buffer in self.nvim.api.list_bufs():
            filepath = Path(buffer.api.get_name())
            if filepath.name == "todoist":
                # We found a 'todoist' buffer. We delete it.
                # self.nvim.api.buf_delete(buffer.number, {"force": True})
                self.nvim.command(f"bdelete! {buffer.number}")
                break
        self.nvim.api.command("enew")
        self.nvim.api.command("set filetype=todoist")
        self.nvim.api.command("file todoist")  # Set the filename.

    def _get_current_line_index(self):
        return self.nvim.eval("line('.')")

    def _get_number_of_lines(self):
        return self.nvim.current.buffer.api.line_count()


class ParsedBuffer:
    def __init__(self, lines: List[str]):
        self._raw_lines = lines

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


class ParsedBufferOld:
    def __init__(self, todoist_api):
        self.todoist = todoist_api
        self.projects = self._init_projects()

        self.projects_by_id = {
            project["id"]: Project(project)
            for project in self.todoist.state["projects"]
        }
        self.lines = self._init_lines()

    def __getitem__(self, i):
        return self.lines[i]

    def line_to_project(self, i: int):
        for line in self.lines[i:0:-1]:
            if isinstance(line, Project):
                project = line
                return project

    def _init_projects(self):
        project_to_tasks = {
            project["id"]: [] for project in self.todoist.state["projects"]
        }
        for task in self.itertasks():
            project_id = task["project_id"]
            project_to_tasks[project_id].append(task)

        return {
            project_id: TasksWorld(tasks)
            for (project_id, tasks) in project_to_tasks.items()
        }

    def __iter__(self):
        yield from self.lines

    def _init_lines(self):
        lines = []
        for project_id, task_world in self.projects.items():
            project = self.projects_by_id[project_id]
            project_name = project["name"]

            lines.append(project)
            lines.append(ProjectUnderline(project_name))
            lines.extend([item for item in task_world])
            lines.append(ProjectSeparator())

        return lines

    def iterstr(self):
        for item in self:
            yield str(item)

    def itertasks(self):
        for task in self.todoist.state["items"]:
            task = TaskInfo(task)
            if task.is_deleted or task.in_history or task.date_completed:
                continue
            yield task


class Project:
    def __init__(self, name: str = None, data: todoist.models.Project = None):
        assert name is not None or data is not None
        self.name = name
        self.data = data

    @property
    def id(self):
        return self.data["id"]

    def __str__(self):
        return self.name

    def __repr__(self) -> str:
        return f"Project: {self.name}"


class Task:
    def __init__(self, content: str = None, data: todoist.models.Item = None):
        assert content is not None or data is not None
        self.content = content
        self.data = data
        self.depth = 0

    @property
    def id(self):
        if self.data is not None:
            return self.data["id"]
        return "[Not synced]"

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


class AddDiff:
    def __init__(self, index, new_lines):
        self.index = index
        self.new_lines = new_lines

    def __repr__(self):
        return f"AddDiff: {self.new_lines}"


class ChangeDiff:
    def __init__(self, index, new_lines):
        self.index = index
        self.new_lines = new_lines

    def __repr__(self):
        return f"ChangeDiff: {self.new_lines}"


class DeleteDiff:
    def __init__(self, index_range):
        self.index_range = index_range


def get_diffs(lhs, rhs):
    raw_diff = get_raw_diff(lhs, rhs)
    return interpret_raw_diff(raw_diff)


def get_raw_diff(lhs, rhs):
    if lhs is None or rhs is None:
        return ""
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
    ).stdout.decode()[
        :-1
    ]  # Trimming the last "\n"

    return diff_output


def interpret_raw_diff(diff):
    if diff == "":
        return []

    to_return = []
    diff_lines = diff.split("\n")
    k = 0
    add_regex = re.compile(r"^(?P<start>\d+)a(?P<from>\d+)(,(?P<to>\d+))?$")
    add_regex = re.compile(r"^(?P<index>\d+)a$")
    change_regex = re.compile(r"^(?P<index>\d+)c$")
    delete_regex = re.compile(r"^(?P<from>\d+)(,(?P<to>\d+))?d$")
    while k < len(diff_lines):
        line = diff_lines[k]
        if "a" in line:
            # 'Add'  mode.
            index = int(add_regex.match(line).group("index"))
            new_lines = []
            k += 1
            while diff_lines[k] != ".":
                new_lines.append(diff_lines[k])
                k += 1
            to_return.append(AddDiff(index, new_lines))
            k += 1
        elif "d" in line:
            # 'delete'  mode.
            matches = delete_regex.match(line)
            from_ = int(matches.group("from"))
            to_ = matches.group("to")
            if to_ is None:
                to_ = from_
            to_ = int(to_)
            index_range = range(from_, to_ + 1)
            to_return.append(DeleteDiff(index_range))
            k += 1
        elif "c" in line:
            index = int(change_regex.match(line).group("index"))
            new_lines = []
            k += 1
            while diff_lines[k] != ".":
                new_lines.append(diff_lines[k])
                k += 1
            to_return.append(ChangeDiff(index, new_lines))
            k += 1

    return to_return


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
