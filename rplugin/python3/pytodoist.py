import os
from typing import List
from copy import copy, deepcopy
from dataclasses import dataclass

import neovim
import todoist

NULL = "null"


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
        for root_task in root_tasks:
            yield from self.__dfs(root_task)

    def _initialize_tasks(self):
        # Initial pass: connecting the Dict id --> task.
        for task in self.tasks:
            self.id_to_task[task.id] = task

        # Second pass: connecting parent to children and vice-versa.
        for task in self.tasks:
            if task["parent_id"] is not None:
                task.parent = self.id_to_task[task["parent_id"]]
                task.parent.children.append(task)

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
        self.is_active = os.environ.get("DEBUG_TODOIST", False)
        self.history = []
        self.history_index = 1
        if self.is_active:
            if not os.environ.get("TODOIST_API_KEY"):
                raise ValueError("Can't find the TODOIST_API_KEY env var.")
            self.todoist = todoist.TodoistAPI(os.environ.get("TODOIST_API_KEY"))
            self.todoist.sync()

    # @neovim.autocmd('BufEnter', eval='expand("<afile")', pattern='*.py', sync=True)
    # def autocmd_more_test(self, filename):
    #    self.nvim.current.line = f"I have no idea what I'm doing. Oh, btw: {filename}"

    @neovim.autocmd("InsertEnter", pattern="todoist", sync=False)
    def register_current_line(self):
        if self.is_active:
            line = self.nvim.current.line.strip()
            self.current_task = self.tasks[line] if line else None
            # self.current_task = self.tasks[self._get_current_line_index() - 1]

    @neovim.autocmd("InsertLeave", pattern="todoist", sync=False)
    def register_updated_line(self):
        if self.is_active:
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
        return new_task

    def _delete_task(self, content: str, update_history: bool = True):
        task = self.tasks[content]
        task_id = task["id"]
        if update_history:
            self._history_append(prev_state=deepcopy(task), new_state=None)

        #self.nvim.command(f"""echom "About to delete\n{task['content']}" """)
        self.todoist.items.delete(task_id)
        self.todoist.commit()
        del self.tasks[content]

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
            self.todoist.items.move(task_id, parent_id=parent_id)
            self.todoist.commit()

        # return updated_task

    @neovim.function("LoadTasks", sync=True)
    def load_tasks(self, args):
        if self.is_active:
            self._clear_buffer()
            self.todoist.sync()

            self.tasks = {}
            self.tasks_world = TasksWorld(self.todoist.state["items"])
            for i, task in enumerate(self.tasks_world):
                self.tasks[task.content] = task.data
                to_print = str(task)
                if i == 0:
                    self.nvim.current.line = to_print
                else:
                    self.nvim.current.buffer.append(to_print)
        else:
            self.nvim.command(
                'echo "The env var DEBUG_TODOIST is not set. Not doing anything."'
            )

    @neovim.function("DeleteTask", sync=False, range=True)
    def delete_task(self, args, range):
        if self.is_active:
            lines = self.nvim.current.buffer[range[0]-1:range[1]]
            self.nvim.command(f"{range[0]},{range[1]} d")
            for i, line in enumerate(lines):
                self._delete_task(line.strip())
        else:
            self.nvim.command(
                'echo "The env var DEBUG_TODOIST is not set. Not doing anything."'
            )

    @neovim.function("CompleteTask")
    def complete_task(self, args):
        if self.is_active:
            line = self.nvim.current.line
            self._complete_task(line)
            self.nvim.command("d")
        else:
            self.nvim.command(
                'echo "The env var DEBUG_TODOIST is not set. Not doing anything."'
            )

    @neovim.function("MakeChild")
    def make_child(self, args):
        line = self.nvim.current.line
        current_task = self.tasks[line.strip()]

        idx = self._get_current_line_index() - 1
        parent_line = self.nvim.current.buffer[idx - 1]
        parent_task = self.tasks[parent_line.strip()]

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
        #self.nvim.api.buf_delete(0, {"force": True})
        self.nvim.api.command("enew")
        self.nvim.api.command("set filetype=todoist")
        self.nvim.api.command("file todoist")  # Set the filename.

    def _get_current_line_index(self):
        return self.nvim.eval("line('.')")

    def _get_number_of_lines(self):
        return self.nvim.current.buffer.api.line_count()
