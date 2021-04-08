import os
import re
from pathlib import Path
from typing import List
from copy import copy, deepcopy
from dataclasses import dataclass

import neovim
import todoist

NULL = "null"
SMART_TAG = True


class World:
    def __init__(self, todoist_api):
        self.todoist = todoist_api
        self.projects = self._init_projects()

        self.project_id_to_name = {
            project["id"]: project["name"] for project in self.todoist.state["projects"]
        }

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

    def iterprint(self):
        for project_id, task_world in self.projects.items():
            project_name = self.project_id_to_name[project_id]
            yield project_name
            yield "=" * len(project_name)
            yield from task_world.iterprint()
            yield ""  # Skipping a line.

    def itertasks(self):
        yield from [
            task
            for task in self.todoist.state["items"]
            if not (task["is_deleted"] or task["in_history"] or task["date_completed"])
        ]


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
        root_tasks = sorted(root_tasks, key=lambda task: task.date)[::-1]
        # root_tasks = [task for task in root_tasks if task.date >= '2021-04-04']
        for root_task in root_tasks:
            yield from self.__dfs(root_task)

    def iterprint(self):
        for task in self:
            yield str(task)

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

    # @neovim.autocmd('BufEnter', eval='expand("<afile")', pattern='*.py', sync=True)
    # def autocmd_more_test(self, filename):
    #    self.nvim.current.line = f"I have no idea what I'm doing. Oh, btw: {filename}"

    @neovim.autocmd("InsertEnter", pattern="todoist", sync=False)
    def register_current_line(self):
        line = self.nvim.current.line.strip()
        self.current_task = self.tasks[line] if line else None
        # self.current_task = self.tasks[self._get_current_line_index() - 1]

    @neovim.autocmd("InsertLeave", pattern="todoist", sync=False)
    def register_updated_line(self):
        new_task_content = self.nvim.current.line.strip()
        if self.current_task is not None:
            updated_task = self._update_task(self.current_task, new_task_content)
        else:
            if new_task_content:
                updated_task = self._create_task(new_task_content)

    def _history_append(self, prev_state, new_state):
        self.history_index = max(1, self.history_index)
        while self.history_index > 1 and len(self.history) > 0:
            del self.history[-self.history_index]
            self.history_index -= 1
        self.history.append({"prev_state": prev_state, "new_state": new_state})

    def _create_task(self, new_content: str, update_history: bool = True):
        new_task = self.todoist.quick.add(new_content)
        self.tasks[new_content] = new_task
        if update_history:
            self._history_append(prev_state=None, new_state=new_task)
        self.tasks_world = TasksWorld(self.tasks.values())
        self._refresh_colors()
        return new_task

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
        for i, line in enumerate(self.world.iterprint()):
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
            project_name = project["name"].replace(" ", "").replace("-", "")
            project_color = COLORS_ID_TO_HEX[project["color"]]
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


COLORS_ID_TO_HEX = {
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
