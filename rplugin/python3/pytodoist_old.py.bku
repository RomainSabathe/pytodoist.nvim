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

    def __str__(self):
        return "=" * len(self.project_name)


class ProjectSeparator:
    def __init__(self):
        pass

    def __str__(self):
        return ""


# class World:
#     pass


# class WorldFromLines:
#     def __init__(self, lines: List[str]):
#         self.lines = self._parse_lines(lines)

#     def _parse_lines(self, lines: List[str]):
#         pass


class World:
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


class TasksWorld(List):
    def __init__(
        self, tasks: List[todoist.models.Item], only_show_active_tasks: bool = True
    ):
        self._raw_tasks = [
            task
            for task in tasks
            if not (task["is_deleted"] or task["in_history"] or task["date_completed"])
        ]
        self.tasks = [TaskInfo(task) for task in self._raw_tasks]

        self.id_to_task = {}
        self.id_to_children_id = {task["id"]: [] for task in self._raw_tasks}
        self.id_to_depth = {task["id"]: [] for task in self._raw_tasks}
        self._initialize_tasks()

    def __repr__(self) -> str:
        return str(self.tasks)

    def __getitem__(self, i):
        return self.tasks[i]

    def __iter__(self):
        root_tasks = [task for task in self.tasks if task.parent is None]
        # TODO: have multiple sorting options?
        root_tasks = sorted(root_tasks, key=lambda task: task.date)[::-1]
        root_tasks = sorted(root_tasks, key=lambda task: task["child_order"])
        # root_tasks = [task for task in root_tasks if task.date >= '2021-04-04']
        for root_task in root_tasks:
            yield from self.__dfs(root_task)

    def _initialize_tasks(self):
        # Initial pass: connecting the Dict id --> task.
        for task in self.tasks:
            self.id_to_task[task.id] = task

        # Second pass: connecting parent to children and vice-versa.
        for task in self.tasks:
            if task["parent_id"] is not None:
                try:
                    task.parent = self.id_to_task[task["parent_id"]]
                    task.parent.children.append(task)
                except KeyError:
                    continue

        # Third pass: determining depth.
        root_tasks = [task for task in self.tasks if task.parent is None]
        for root_task in root_tasks:
            self.__dfs(root_task)  # This sets the depth.

    def __dfs(self, task, depth=0):
        task.depth = depth
        yield task
        for child in task.children:
            yield from self.__dfs(child, depth + 1)


class Project(todoist.models.Project):
    def __init__(self, project):
        self.data = project

    @property
    def id(self):
        return self.data["id"]

    @property
    def name(self):
        return self.data["name"]

    def __str__(self):
        return self.name

    def __repr__(self) -> str:
        return f"Project: {self.name}"


class TaskInfo(todoist.models.Item):
    def __init__(
        self,
        task: todoist.models.Item,
        depth: int = 0,
        children: List = None,
        parent=None,
    ):
        self.data = task
        self.depth = depth
        self.children = children if children is not None else []
        self.parent = parent

    @property
    def id(self):
        return self.data["id"]

    @property
    def content(self):
        return self.data["content"]

    @property
    def date(self):
        return self.data["date_added"]

    @property
    def date_completed(self):
        return self.data["date_completed"]

    @property
    def in_history(self):
        return self.data["in_history"]

    @property
    def is_deleted(self):
        return self.data["is_deleted"]

    def __repr__(self) -> str:
        short_content = (
            self.content if len(self.content) < 50 else f"{self.content[:47]}..."
        )
        return f"TaskInfo #{self.id}: {short_content}"

    def __str__(self):
        buffer = ""
        for _ in range(self.depth):
            buffer += "    "
        buffer += self.content
        return buffer


@neovim.plugin
class Main(object):
    def __init__(self, nvim):
        self.nvim = nvim
        self.history = []
        self.history_index = 1
        if not os.environ.get("TODOIST_API_KEY"):
            raise ValueError("Can't find the TODOIST_API_KEY env var.")
        self.todoist = todoist.TodoistAPI(os.environ.get("TODOIST_API_KEY"))
        self.todoist.sync()

        self.last_buffer = None

        # self.last_position = None

    # @neovim.autocmd('BufEnter', eval='expand("<afile")', pattern='*.py', sync=True)
    # def autocmd_more_test(self, filename):
    #    self.nvim.current.line = f"I have no idea what I'm doing. Oh, btw: {filename}"

    def _get_buffer_content(self) -> str:
        return "\n".join(self.nvim.current.buffer[:])

    @neovim.autocmd("InsertEnter", pattern="todoist", sync=False)
    def register_current_line(self):
        line = self.nvim.current.line.strip()
        self.current_task = self.tasks[line] if line else None

        self.last_buffer = copy(self._get_buffer_content())
        # self.current_task = self.tasks[self._get_current_line_index() - 1]

    # @neovim.autocmd("CursorMoved,CursorMovedI", pattern="todoist", sync=False)
    # def on_move(self):
    #     if self.last_position is None:
    #         self.last_position = self._get_current_line_index()

    @neovim.autocmd("CursorMoved", pattern="todoist", sync=True)
    def cursor_moved(self):
        if self.last_buffer is None:
            self.last_buffer = copy(self._get_buffer_content())
        # self.nvim.command(f"echom 'hello'")
        self.register_updated_line()

    @neovim.autocmd("InsertLeave", pattern="todoist", sync=True)
    def register_updated_line(self):
        # self.nvim.command(f"echom 'hello2'")
        new_buffer = copy(self._get_buffer_content())
        diffs = get_diffs(self.last_buffer, new_buffer)
        # self.nvim.command(f"""echom ' "{diffs} " '""")
        # self.nvim.command(f"""echom '{len(diffs)}'""")
        for diff in diffs:
            # self.nvim.command(f"""echom ' "{diff} " '""")
            if isinstance(diff, AddDiff):
                index = diff.index - 1
                associated_project = self.world.line_to_project(index)
                for line in diff.new_lines:
                    self._create_task(line, project=associated_project)
            elif isinstance(diff, ChangeDiff):
                index = diff.index - 1
                new_line = diff.new_lines[0]
                self.nvim.command(f"""echom '{new_line}'""")
                item = self.world[index]
                self.nvim.command(f"""echom '{item}'""")
                # self.nvim.command(f"""echom '{type(item)}'""")
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

        # if len(diffs) > 0:
        #     self.world = World(self.todoist)

        # new_task_content = self.nvim.current.line.strip()
        # if self.current_task is not None:
        #     updated_task = self._update_task(self.current_task, new_task_content)
        # else:
        #     if new_task_content:
        #         updated_task = self._create_task(new_task_content)

    def _history_append(self, prev_state, new_state):
        self.history_index = max(1, self.history_index)
        while self.history_index > 1 and len(self.history) > 0:
            del self.history[-self.history_index]
            self.history_index -= 1
        self.history.append({"prev_state": prev_state, "new_state": new_state})

    def _create_task(
        self, content: str, project: Project = None, update_history: bool = True
    ):
        if project is not None:
            content = f"#{project.name} {content}"
        new_task = self.todoist.quick.add(content)
        # # No need to do todoist.commit() when adding new tasks.
        # self.tasks[content] = new_task
        # if update_history:
        #     self._history_append(prev_state=None, new_state=new_task)
        # self.tasks_world = TasksWorld(self.tasks.values())
        # self._refresh_colors()
        # return new_task

    def _delete_task(self, content: str, update_history: bool = True):
        task = self.tasks[content]
        task_id = task["id"]
        if update_history:
            self._history_append(prev_state=deepcopy(task), new_state=None)

        # self.nvim.command(f"""echom "About to delete\n{task['content']}" """)
        self.todoist.items.delete(task_id)
        self.todoist.commit()
        del self.tasks[content]
        self.tasks_world = TasksWorld(self.tasks.values())

    def _complete_task(self, content: str, update_history: bool = True):
        task = self.tasks[content]
        task_id = task["id"]

        updated_task = self.todoist.items.complete(task_id)
        self.todoist.commit()
        if update_history:
            self._history_append(
                prev_state=deepcopy(task), new_state=deepcopy(updated_task)
            )
        del self.tasks[content]
        self.tasks_world = TasksWorld(self.tasks.values())

    # TODO: implement a NamedTuple as history items.

    def _update_task(
        self,
        task,
        new_content: str = None,
        parent_id: int = None,
        update_history: bool = True,
    ):
        task_id = task["id"]
        old_task_content = task["content"]

        # Changing the 'content'
        if new_content:
            if SMART_TAG and ("@" in new_content or "#" in new_content):
                updated_task = self._create_task(new_content, update_history=False)
                if task["parent_id"] is not None:
                    self.todoist.items.move(
                        updated_task["id"], parent_id=task["parent_id"]
                    )
                    updated_task["parent_id"] = task["parent_id"]
                self.tasks[new_content] = updated_task

                self._delete_task(old_task_content, update_history=False)
                if update_history:
                    self._history_append(
                        prev_state=deepcopy(task), new_state=deepcopy(updated_task)
                    )
            else:
                # Updating the buffer `self.tasks`
                updated_task = deepcopy(task)
                updated_task["content"] = new_content
                if update_history:
                    self._history_append(
                        prev_state=deepcopy(task), new_state=deepcopy(updated_task)
                    )

                del self.tasks[old_task_content]
                self.tasks[new_content] = deepcopy(updated_task)

                # Updating Todoist.
                # self.nvim.command(f"""echo "About to replace\n{task['content']}\nwith\n{new_content}" """)
                self.todoist.items.update(task_id, content=new_content)
                self.todoist.commit()
                # self.nvim.command(f'echo "Old line was: {self.old_line}. New line is: {self.new_line}"')

        # Changing the 'parent'
        if parent_id:
            if parent_id == NULL:
                parent_id = None
            self.tasks[old_task_content]["parent_id"] = parent_id
            self.todoist.items.move(task_id, parent_id=parent_id)
            self.todoist.commit()

        # return updated_task
        self.tasks_world = TasksWorld(self.tasks.values())
        self._refresh_colors()

    @neovim.function("LoadTasks", sync=True)
    def load_tasks(self, args):
        self._clear_buffer()
        self.todoist.sync()
        self._setup_colors()

        self.project_name_to_id = {
            project["name"]: project["id"] for project in self.todoist.state["projects"]
        }
        self.label_name_to_id = {
            label["name"]: label["id"] for label in self.todoist.state["labels"]
        }
        tasks = self.todoist.state["items"]
        if args:
            query = args[0]
            tasks = self._filter_tasks(query, tasks)

        # tasks = pd.DataFrame([item.data for item in self.todoist.state["items"]])
        # projects = pd.DataFrame(
        #     [project.data for project in self.todoist.state["projects"]]
        # )
        # tasks = tasks.merge(
        #     projects.set_index("id").rename(columns={"name": "project_name"})[
        #         ["project_name"]
        #     ],
        #     left_on="project_id",
        #     right_index=True,
        #     suffixes=("", "_project"),
        # )

        self.tasks = {task["content"]: task for task in tasks}
        self.tasks_world = TasksWorld(tasks)
        self.world = World(self.todoist)
        for i, line in enumerate(self.world.iterstr()):
            if i == 0:
                self.nvim.current.line = line
            else:
                self.nvim.current.buffer.append(line)

        # for i, task in enumerate(self.tasks_world):
        #     self.tasks[task.content] = task.data
        #     to_print = str(task)
        #     if i == 0:
        #         self.nvim.current.line = to_print
        #     else:
        #         self.nvim.current.buffer.append(to_print)

        self._refresh_colors()

    def _setup_colors(self):
        for project in self.todoist.state["projects"]:
            project_name = (
                project["name"].replace(" ", "").replace("-", "").replace(".", "")
            )
            project_color = BG_COLORS_ID_TO_HEX[project["color"]]
            # fg_color = FG_COLORS_ID_TO_HEX[project["color"]]
            # self.nvim.command(f"""echom '{project_name}'""")
            self.nvim.command(
                # f"highlight Project{project_name} ctermbg={project_color} guibg={project_color}"
                f"highlight Project{project_name} guifg={project_color}"
            )

    def _refresh_colors(self):
        buffer = self.nvim.current.buffer
        for i, line in enumerate(buffer):
            task = self.tasks.get(line.strip())
            if task is None:
                # No higlighting for this line.
                continue
            project_id = task["project_id"]
            project_name = (
                [
                    project["name"]
                    for project in self.todoist.state["projects"]
                    if project["id"] == project_id
                ][0]
                .replace(" ", "")
                .replace("-", "")
                .replace(".", "")
            )
            buffer.add_highlight(f"Project{project_name}", i, 0, -1)

    @neovim.function("DeleteTask", sync=False, range=True)
    def delete_task(self, args, range):
        lines = self.nvim.current.buffer[range[0] - 1 : range[1]]
        self.nvim.command(f"{range[0]},{range[1]} d")
        for i, line in enumerate(lines):
            self._delete_task(line.strip())

    @neovim.function("CompleteTask")
    def complete_task(self, args):
        line = self.nvim.current.line
        self._complete_task(line)
        self.nvim.command("d")

    @neovim.function("MakeChild")
    def make_child(self, args):
        line = self.nvim.current.line
        current_task = self.tasks[line.strip()]

        idx = self._get_current_line_index() - 1
        if idx == 0:
            return
        depth_current_task = self.tasks_world.id_to_task[current_task["id"]].depth

        task_above = None
        offset, depth_task_above = 0, -1
        while depth_task_above != depth_current_task:
            offset += 1
            line_above = self.nvim.current.buffer[idx - offset]
            task_above = self.tasks[line_above.strip()]
            depth_task_above = self.tasks_world.id_to_task[task_above["id"]].depth

        parent_task = task_above
        self.nvim.command(">1")
        self._update_task(current_task, parent_id=parent_task["id"])

    @neovim.function("UnmakeChild")
    def unmake_child(self, args):
        line = self.nvim.current.line
        current_task = self.tasks[line.strip()]

        parent_id = current_task["parent_id"]
        parent_tasks = [task for task in self.tasks.values() if task["id"] == parent_id]
        parent_task = parent_tasks[0]  # There should only be one anyway.
        grand_father_id = parent_task["parent_id"]
        if grand_father_id is None:
            # In this lib, None is reserved for no actions. However, having a 'parent_id'
            # that equals to None is a meaningful information. We interpret it as NULL.
            grand_father_id = NULL

        self.nvim.command("<1")
        self._update_task(current_task, parent_id=grand_father_id)

    @neovim.function("Undo")
    def undo(self, args):
        # self.nvim.command(f'echo "{str(self.history)}"')
        if self.history:
            prev_state, new_state = (
                self.history[-self.history_index]["prev_state"],
                self.history[-self.history_index]["new_state"],
            )
            if prev_state is None:
                # Last action was a task creation.
                self._delete_task(new_state["content"], update_history=False)
            elif new_state is None:
                # Last action was a task deletion.
                self._create_task(prev_state["content"], update_history=False)
            else:
                # Last action was a task modification.
                self._update_task(
                    new_state, prev_state["content"], update_history=False
                )
            # self.history.append({"prev_state": new_state, "new_state": prev_state})
            self.history_index += 1
        self.nvim.command("u")

    @neovim.function("Redo")
    def redo(self, args):
        # self.nvim.command(f'echo "{str(self.history)}"')
        if self.history:
            prev_state, new_state = (
                self.history[-self.history_index + 1]["prev_state"],
                self.history[-self.history_index + 1]["new_state"],
            )
            if prev_state is None:
                # Last action was a task creation.
                self._create_task(new_state["content"], update_history=False)
            elif new_state is None:
                # Last action was a task deletion.
                self._delete_task(prev_state["content"], update_history=False)
            else:
                # Last action was a task modification.
                self._update_task(
                    prev_state, new_state["content"], update_history=False
                )
            # self.history.append({"prev_state": new_state, "new_state": prev_state})
            self.history_index -= 1
        self.nvim.command("red")

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

    def _filter_tasks(self, query, tasks):
        tasks = deepcopy(tasks)

        # Fetching the projects.
        pattern = r"#(?P<project_name>\w+)"
        for project_name in re.findall(pattern, query):
            project_id = [
                project["id"]
                for project in self.todoist.state["projects"]
                if project["name"].lower() == project_name
            ][0]
            idx_to_delete = []
            for i, task in enumerate(tasks):
                if task["project_id"] != project_id:
                    idx_to_delete.append(i)
            for idx in idx_to_delete[::-1]:
                del tasks[idx]

        # Special filtering: Removing everything that has a label
        if "no label" in query:
            idx_to_delete = []
            for i, task in enumerate(tasks):
                if task["labels"]:
                    idx_to_delete.append(i)
                    continue
            for idx in idx_to_delete[::-1]:
                del tasks[idx]

        # Fetching the labels.
        pattern = r"(not)? @(?P<label_name>\w+)"
        for (is_negation, label_name) in re.findall(pattern, query):
            label_id = [
                label["id"]
                for label in self.todoist.state["labels"]
                if label["name"].lower() == label_name
            ][0]
            idx_to_delete = []
            for i, task in enumerate(tasks):
                if any([candidate == label_id for candidate in task["labels"]]):
                    if is_negation:
                        idx_to_delete.append(i)
                    continue
                if not is_negation:
                    idx_to_delete.append(i)
            for idx in idx_to_delete[::-1]:
                del tasks[idx]

        return tasks


def find_best_fg_colour(bg_color):
    from colour import Color

    return "#ffffff" if Color(bg_color).luminance < 0.5 else "#000000"

    best_score, best_color = 0.0, None
    for luminance in range(255):
        val = luminance / 255
        proposal = Color(rgb=(val, val, val))
        score = contrast_score(proposal, bg_color)
        if score > best_score:
            best_color = proposal.hex
    return best_color


def contrast_score(fg_color, bg_color):
    from colour import Color

    score = (Color(fg_color).luminance + 0.05) / (Color(bg_color).luminance + 0.05)
    if score < 1.0:
        score = 1 / score
    return score


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

# FG_COLORS_ID_TO_HEX = {
#     id: find_best_fg_colour(color) for id, color in BG_COLORS_ID_TO_HEX.items()
# }
