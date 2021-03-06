import os
import re
import subprocess
from pathlib import Path
from collections import deque
from abc import abstractmethod
from copy import copy, deepcopy
from dataclasses import dataclass
from typing import List, Optional, Union, Callable

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
            todoist.TodoistAPI(os.environ.get("TODOIST_API_KEY")),
            custom_sections=[
                CustomSection("Today", lambda task: "today" in task.labels),
                CustomSection("This Week", lambda task: "thisweek" in task.labels),
            ],
        )
        self.parsed_buffer_since_last_save = None
        self.parsed_buffer = None

    def _get_buffer_content(self) -> List[str]:
        return self.nvim.current.buffer[:]

    @pynvim.autocmd("InsertEnter", pattern=".todoist", sync=False)
    def register_current_line(self):
        pass

    @pynvim.autocmd("TextYankPost", pattern=".todoist", sync=False)
    def text_yank_post(self):
        self._refresh_parsed_buffer()
        self._refresh_highlights()

    @pynvim.autocmd("InsertLeave", pattern=".todoist", sync=False)
    def insert_leave(self):
        self._refresh_parsed_buffer()
        self._refresh_highlights()

    @pynvim.autocmd("TextChanged", pattern=".todoist", sync=False)
    def text_changed(self):
        self._refresh_parsed_buffer()
        self._refresh_highlights()

    @pynvim.function("CompleteTask")
    def complete_task(self, args):
        line_index = self._get_current_line_index()
        task = self.parsed_buffer[line_index - 1]
        self.nvim.command("echo 'Task registered as completed.'")
        task.complete(impact_remote=False)
        self.nvim.command("d")

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
        self._refresh_parsed_buffer()
        self._setup_highlight_groups()
        self._refresh_highlights()
        # self.load_tasks(None)

    @pynvim.autocmd("InsertLeave", pattern=".todoist", sync=True)
    def register_updated_line(self):
        pass

    def _refresh_parsed_buffer(self):
        self.parsed_buffer = ParsedBuffer(self._get_buffer_content(), self.todoist)
        self._force_formatting()

    def _force_formatting(self):
        for i, (line, item) in enumerate(
            zip(self.nvim.current.buffer[:], self.parsed_buffer)
        ):
            if isinstance(item, Task):
                # The `line` can sometimes be ill-formed, like `Task 10` instead of
                # `[ ] Task 10`.
                # This likely happens when the user is inserting multiple
                # tasks in a row without pressing "<esc>o" between each entry.
                # Re-parsing the task and re-printing it (if needed) will enforce that
                # we always have properly formated tasks.
                task = Task.parse(line)
                if str(task) != line:
                    # Reprinting if necessary. This shouldn't affect many lines.
                    self.nvim.current.buffer[i] = str(task)

    def _input_from_fzf(self, source: List[str]) -> str:
        # This command instantiates a global vimscript variable named `fzf_output`.
        self.nvim.api.command("call ResetFzfOutput()")
        self.nvim.api.command(
            "call fzf#run(fzf#wrap({"
            "'sink': function('CaptureFzfOutput'),"
            f"'source': {source}"
            "}))"
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
        if len(args) == 0:
            self.nvim.api.command("set modifiable")
            projects = [project.name for project in self.todoist.projects]
            project_name = self._input_from_fzf(source=projects)
        else:
            project_name = args[0]
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

        # Counting the number of lines that we want to move.
        change_amplitude = _range[1] - _range[0] + 1

        # We need to paste the line(s) at position `i + j `.
        # First, copying.
        self.nvim.api.command(f"{_range[0]},{_range[1]}y")
        self.nvim.api.command(f"{i+j}pu")
        # Then, deleting the original task.
        # We need to be extra careful in case we move a task upwards in the buffer.
        # In that case, the range of deletion has been shifted.
        delta = 0 if _range[0] < i + j else change_amplitude
        self.nvim.api.command(f"{_range[0]+delta},{_range[1]+delta}d")
        self.nvim.api.command(
            f"call setpos('.',"
            f"[{buf_index}, {line_index+delta}, {col_index}, {offset}]"
            ")"
        )

    @pynvim.function("AssignLabel", sync=False, range=False)
    def assign_label(self, args):
        if len(args) == 0:
            self.nvim.api.command("set modifiable")
            # TODO: create a Label wrapper class?
            labels = [label["name"] for label in self.todoist.api.state["labels"]]
            label_name = self._input_from_fzf(source=labels)
        else:
            label_name = args[0]
        if label_name == "":
            return

        # Getting the task at the current cursor position.
        line_index = self._get_current_line_index()
        task = self.parsed_buffer[line_index - 1]

        # Getting the label we want to assign (we need its id).
        label = self.todoist.get_label_by_name(label_name)

        # Getting the list of current labels (we want to append to that list).
        current_labels = task.labels
        task.update(labels=[label["id"], *current_labels])
        self.nvim.command(f"echo 'Task registered with label: {label['name']}.'")

        # # TODO: still unsure if we want to do this...
        # # item.move(project_id=project.id)

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
        # Creating or loading the buffer.
        if not self._todoist_buffer_exists():
            self._create_todoist_buffer()
        self._set_todoist_buffer_as_current()

        # Storing the cursor position.
        self.nvim.api.command("let position = getcurpos()")
        buf_index, line_index, col_index, offset, _ = self.nvim.api.eval("position")

        # Actually writing the tasks.
        self.todoist.sync()
        self.nvim.current.buffer[:] = [str(item) for item in self.todoist]

        # Restoring the cursor position.
        # We need to be mindful of the case where there were changes on the Todoist
        # server, and we end up with a new buffer that has less lines than before.
        new_line_index = min(line_index, len(self.nvim.current.buffer) - 1)
        self.nvim.api.command(
            f"call setpos('.', [{buf_index}, {new_line_index}, {col_index}, {offset}])"
        )

        # Cancel the "modified" state of the buffer.
        # TODO: clean this.
        # TODO: before doing this; check that the buffer is not in a modified state.
        self.parsed_buffer_since_last_save = None  # Prevents remote updated.
        self.nvim.api.command("w!")
        self.parsed_buffer_since_last_save = ParsedBuffer(
            self._get_buffer_content(), self.todoist
        )
        self._refresh_parsed_buffer()
        self._setup_highlight_groups()
        self._refresh_highlights()

        # Emiting a message to confirm.
        self.nvim.command("echo 'Tasks loaded successfully.'")

    def _todoist_buffer_exists(self):
        for i, buffer in enumerate(self.nvim.buffers):
            filepath = Path(buffer.name)
            if filepath.name == ".todoist":
                return True
        return False

    def _set_todoist_buffer_as_current(self):
        for i, buffer in enumerate(self.nvim.buffers):
            filepath = Path(buffer.name)
            if filepath.name == ".todoist":
                # We found a 'todoist' buffer. We jump to it.
                self.nvim.current.buffer = buffer
                return

    def _create_todoist_buffer(self):
        self.nvim.command("noswapfile enew")
        self.nvim.command("set filetype=todoist")
        self.nvim.command("file .todoist")  # Set the filename.

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
                    f"highlight {group_name} " f"gui=NONE " f"guifg={item.rgbcolor}"
                )
                # Adding a specific case for when the task is completed.
                group_name = f"TasksComplete{sanitize_str(item.name)}"
                self.nvim.api.command(
                    f"highlight {group_name} "
                    f"cterm=strikethrough gui=strikethrough "
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
            elif isinstance(item, Task) and item.is_complete:
                highlight_group = f"TasksComplete{highlight_group_suffix}"
            else:
                highlight_group = f"Tasks{highlight_group_suffix}"
            self.nvim.current.buffer.add_highlight(highlight_group, i, 0, -1)

    def echo(self, message: str):
        # Type `:help nvim_echo` for more info about the args.
        self.nvim.api.echo([[str(message), ""]], True, {})


class Project:
    def __init__(
        self,
        name: str = None,
        data: todoist.models.Project = None,
        children: List["Project"] = None,
    ):
        assert name is not None or data is not None
        self.name = name
        self.data = data
        if children is None:
            self.children = []

        if data is not None and name is None:
            self.name: str = data["name"]

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

    @property
    def isroot(self):
        if self.data is not None:
            return self.data["parent_id"] is None
        return True

    @property
    def rgbcolor(self):
        if self.data is not None:
            return BG_COLORS_ID_TO_HEX[self.data["color"]]
        return "#ffffff"

    @property
    def is_inbox(self):
        return self.data.data.get("inbox_project")

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


class Label:
    def __init__(self, name: str = None, data: todoist.models.Label = None):
        assert name is not None or data is not None
        self.content = name
        self.data = data

        if data is not None and name is None:
            self.name: str = data["name"]

    def __str__(self):
        return f"@{self.name}"

    def __repr__(self) -> str:
        return f"Label #{self.id}: {self.name}"

    def __eq__(self, other):
        if isinstance(other, Label):
            return self.name == other.name
        elif isinstance(other, str):
            return self.name == other
        elif isinstance(other, int):
            if self.data is None:
                return False
            return self.data["id"] == other
        else:
            raise AttributeError(
                f"Tried to compare a Label with a {type(other)} object."
            )

    @property
    def id(self):
        if self.data is not None:
            return self.data["id"]
        return "[Not synced]"


class Task:
    def __init__(
        self,
        content: str = None,
        is_complete: bool = False,
        data: todoist.models.Item = None,
        labels: List[Label] = None,
        children: List["Project"] = None,
    ):
        assert content is not None or data is not None
        self.content = content
        if data is None:
            data = dict()
        self.data = data
        self.labels = labels
        self.depth = 0
        self.is_complete = is_complete
        if children is None:
            self.children = []

        if data is not None and content is None:
            self.content = data["content"]

    @abstractmethod
    def parse(line: Union[str, "Task"]) -> "Task":
        # A task is formed as one of these  possibilities:
        # [ ] A task
        # [x] A task
        # [X] A task
        # A task
        if isinstance(line, Task):
            return line
        checkbox = r"(\[(?P<status>x|X| )\] )?"
        content = r"(?P<content>.*)"
        labels = r"(?P<label>@\w+)*"
        # TODO: removing the label display for now.
        # pattern = rf"^{checkbox}{content}( | {labels})?$"
        pattern = rf"^{checkbox}{content}$"
        match_results = re.match(pattern, line)

        status = match_results.group("status")
        content = match_results.group("content")

        return Task(content=content, is_complete=status in ["x", "X"])

    @property
    def id(self):
        if isinstance(self.data, todoist.models.Item):
            return self.data["id"]
        return self.data.get("id", "[Not synced]")

    @property
    def child_order(self):
        if isinstance(self.data, todoist.models.Item):
            return self.data["child_order"]
        return self.data.get("child_order", 1)

    @property
    def isroot(self):
        if isinstance(self.data, todoist.models.Item):
            return self.data["parent_id"] is None
        return self.data.get("parent_id", True) is None

    @property
    def labels(self):
        if not self.__labels is None:
            return self.__labels
        if isinstance(self.data, todoist.models.Item):
            return self.data["labels"]
        return self.data.get("labels", [])

    @labels.setter
    def labels(self, labels):
        self.__labels = labels

    def __repr__(self) -> str:
        short_content = (
            self.content if len(self.content) < 50 else f"{self.content[:47]}..."
        )
        return f"Task #{self.id}: {short_content}"

    def __str__(self):
        buffer = ""
        for _ in range(self.depth):
            buffer += "    "
        buffer += "[ ] " if not self.is_complete else "[X] "
        buffer += self.content
        # TODO: removing the label display for now.
        # if self.labels:
        #     buffer += " |"
        #     for label in self.labels:
        #         buffer += f" {label}"
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

    def complete(self, impact_remote: bool = True):
        if impact_remote:
            self.data.complete()
        self.content = "[Completed]"
        self.is_complete = True

    def delete(self, impact_remote: bool = True):
        if impact_remote:
            self.data.delete()
        self.content = "[Deleted]"

    def move(self, *args, **kwargs):
        return self.data.move(*args, **kwargs)


class CustomSection:
    def __init__(self, name: str, filter_fn: Callable[[Task], bool]):
        self.name = name
        self.filter_fn = filter_fn

    def __str__(self):
        return self.name

    def matches(self, task: Task):
        return self.filter_fn(task)


class SectionUnderline:
    def __init__(self, section_name: str):
        self.project_name = section_name

    def __repr__(self):
        return "SectionUnderline"

    def __str__(self):
        return "-" * len(self.project_name)


class ProjectUnderline:
    def __init__(self, project_name: str):
        self.project_name = project_name

    def __repr__(self):
        return "ProjectUnderline"

    def __str__(self):
        return "=" * len(self.project_name)


class TodoistInterface:
    def __init__(
        self,
        todoist_api: todoist.api.TodoistAPI,
        custom_sections: List[CustomSection] = None,
    ):
        self.api = todoist_api
        self.tasks = None
        self.projects = None
        if custom_sections is None:
            custom_sections = []
        self.custom_sections = custom_sections

    def sync(self):
        self.api.sync()
        self.labels = self._init_labels()
        self.projects = self._init_projects()
        self.tasks = self._init_tasks()

    def _init_labels(self):
        labels = [Label(data=item) for item in self.api.state["labels"]]
        return labels

    def _init_projects(self):
        # First pass: not considering the children or anything.
        projects = [Project(data=item) for item in self.api.state["projects"]]

        # Second pass: assigning children.
        for i, project in enumerate(projects):
            if project.data["parent_id"] is not None:
                # Searching for the parent.
                for parent_project in projects:
                    if parent_project.id == project.data["parent_id"]:
                        parent_project.children.append(project)

        return projects

    def _init_tasks(self):
        # First pass: not considering the children or anything.
        tasks = [
            Task(
                data=item,
                labels=[label for label in self.labels if label.id in item["labels"]],
            )
            for item in self.api.state["items"]
        ]

        # Second pass: assigning children.
        for i, task in enumerate(tasks):
            if task.data["parent_id"] is not None:
                # Searching for the parent.
                for parent_task in tasks:
                    if parent_task.id == task.data["parent_id"]:
                        parent_task.children.append(task)

        return tasks

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

    def get_label_by_name(self, name):
        for label in self.api.state["labels"]:
            if name == label["name"]:
                return label
        return None

    def iterprojects(self, root: Project = None):
        if root is not None:
            yield root
            next_projects = sorted(
                root.children, key=lambda project: project.child_order
            )
            for next_project in next_projects:
                yield from self.iterprojects(next_project)
        else:
            root_projects = [project for project in self.projects if project.isroot]
            for project in sorted(
                root_projects, key=lambda project: project.child_order
            ):
                yield from self.iterprojects(root=project)

    def itertasks(self, root: Task = None):
        if root is not None:
            yield root
            next_tasks = sorted(root.children, key=lambda task: task.child_order)
            for next_task in next_tasks:
                yield from self.itertasks(next_task)
        else:
            root_tasks = [task for task in self.tasks if task.isroot]
            for task in sorted(root_tasks, key=lambda task: task.child_order):
                yield from self.itertasks(root=task)

    def __iter__(self):
        for project in self.iterprojects():
            if not project.isvalid():
                continue
            yield project
            yield ProjectUnderline(project_name=project.name)
            # TODO: do the filtering, *then* the sorting. Will be faster.
            # project_tasks = [task for task in self.tasks if task.isin(project)]
            for task in self.itertasks():
                if task.isin(project) and task.isvalid():
                    yield task
            yield ProjectSeparator()

        # We display the custom sections last.
        # TODO: removing the custom sections for now.
        for custom_section in self.custom_sections:
            yield custom_section
            yield SectionUnderline(custom_section.name)
            # In order to preserve task order, we're forced to iterate over projects
            # once again.
            for project in self.iterprojects():
                for task in self.itertasks():
                    if (
                        task.isin(project)
                        and task.isvalid()
                        and custom_section.matches(task)
                    ):
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
        if "parent_id" not in kwargs.keys():
            kwargs["parent_id"] = None
        if "labels" not in kwargs.keys():
            kwargs["labels"] = []
        return self.api.items.add(*args, **kwargs)

    def commit(self):
        return self.api.commit()


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

            # Look ahead: checking if the current line is actually a project or a
            # custom section.
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

            potential_section_name = line
            potential_underline = SectionUnderline(potential_section_name)
            if (
                potential_section_name != ""
                and k + 1 < len(self._raw_lines)
                and str(potential_underline) == self._raw_lines[k + 1]
            ):
                # We are indeed scanning a section. We register this info
                # and move on.
                items.append(CustomSection(name=potential_section_name, filter_fn=None))
                items.append(potential_underline)
                k += 2
                continue

            # The remaining possibilities are: a proper task or a ProjectSeparator.
            item = Task.parse(line) if line.strip() != "" else ProjectSeparator()
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
                    task_in_buffer_is_marked_as_complete = self.items[i].is_complete
                    self.items[i] = task
                    self.items[i].is_complete = task_in_buffer_is_marked_as_complete
            elif isinstance(item, CustomSection):
                break

    def __iter__(self):
        yield from self.items

    def __getitem__(self, i):
        return self.items[i]

    def _get_project_or_section_at_line(self, i: int) -> Union[Project, CustomSection]:
        # We take the first project that we encounter by "moving up" in the document.
        for item in self[:i][::-1]:
            if isinstance(item, (Project, CustomSection)):
                return item
        raise Exception("Couldn't find project.")

    def _get_inbox_project(self):
        if self.todoist is None:
            return None
        candidates = [
            project for project in self.todoist.iterprojects() if project.is_inbox
        ]
        assert len(candidates) != 0, "Can't find an Inbox project."
        assert len(candidates) <= 1, "We found too many inbox projects."
        return candidates[0]

    # TODO: I have to find another name for this.
    # Also: there is a big assumption: `self` should be synced with Todoist (all ids
    # are available) whereas `other` might not be.
    def compare_with(self, other):
        diff = Diff(self, other)

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
                    if str(item_after).strip() == "":
                        # We prevent from adding an empty task
                        continue
                    new_task = Task.parse(item_after)
                    if not new_task.is_complete:
                        # We wan to create a task. There are two cases:
                        # - Either the task is created within a project, and we
                        #   can directly obtain the project_id.
                        # - Or it was added to a custom section. In which case we
                        #   can't know what the project_id should be. Therefore we
                        #   default to Inbox.
                        parent = self._get_project_or_section_at_line(from_index + i)
                        project_id = None  # Will be initialized next.
                        if isinstance(parent, Project):
                            project_id = parent.id
                        elif isinstance(parent, CustomSection):
                            project_id = self._get_inbox_project().id
                        self.todoist.add_task(
                            content=new_task.content, project_id=project_id
                        )
                elif item_after is None or diff_segment.action_type == "d":
                    if isinstance(item_before, Task):
                        if item_before.content == "[Completed]":
                            item_before.complete(impact_remote=True)
                        else:
                            item_before.delete(impact_remote=True)
                else:
                    if isinstance(item_before, Task):
                        new_task = Task.parse(item_after)
                        if not new_task.is_complete:
                            item_before.update(content=new_task.content)
                        else:
                            item_before.complete(impact_remote=True)
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
    def __init__(self, lhs: ParsedBuffer, rhs: ParsedBuffer):
        self.lhs = lhs
        self.rhs = rhs

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

        lines = self.raw_diff  # Shorter name for readibility.
        i_lines = 0
        while i_lines < len(lines):
            matches = reg.match(lines[i_lines])

            if matches.group("action_type") in ["a", "c"]:
                # TODO: understand why I need to define this.
                # delta = -1 if matches.group("action_type") == "c" else 0
                # delta = -1
                modified_items = []
                from_index = int(matches.group("from_index"))
                i_group = 0
                while lines[i_lines] != ".":
                    i_lines += 1
                    # modified_items.append(self.rhs[from_index + i_group + delta])
                    modified_items.append(lines[i_lines])
                    i_group += 1
                modified_items = modified_items[:-1]  # Deleting the last "."
                yield DiffSegment(
                    matches.group("action_type"),
                    matches.group("from_index"),
                    matches.group("to_index"),
                    modified_items,
                )

            elif matches.group("action_type") == "d":
                yield DiffSegment(
                    matches.group("action_type"),
                    matches.group("from_index"),
                    matches.group("to_index"),
                    [],
                )

            i_lines += 1

    @abstractmethod
    def get_raw_diff(self, lhs: ParsedBuffer, rhs: ParsedBuffer):
        # TODO: that's dirty. Ideally we should pipe directly to `diff`.
        path_lhs = Path("/tmp/lhs")
        if path_lhs.exists():
            path_lhs.unlink()
        path_lhs.write_text("\n".join([str(item) for item in lhs]))

        path_rhs = Path("/tmp/rhs")
        if path_rhs.exists():
            path_rhs.unlink()
        path_rhs.write_text("\n".join([str(item) for item in rhs]))

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
    modified_lines: List[Union[str, Task]]

    def __post_init__(self):
        self.from_index: int = int(self.from_index)
        if self.to_index is not None:
            self.to_index: int = int(self.to_index) + 1
        else:
            self.to_index: int = self.from_index + 1

    def __getitem__(self, i: int):
        return self.modified_lines[i]

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
