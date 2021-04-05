import os
from typing import List
from copy import copy, deepcopy
from dataclasses import dataclass

import neovim
import todoist


class TasksWorld:
    def __init__(self, tasks: List[todoist.models.Item] = None):
        self.tasks = []
        self.id_to_task = {}

        if tasks:
            for task in tasks:
                self.append(task)

    def append(self, task: todoist.models.Item):
        pass


@dataclass
class TaskInfo:
    task: todoist.models.Item
    indentation: int = 0

    @property
    def id(self):
        return self.task["id"]

NULL = 'null'


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

    @neovim.autocmd("InsertEnter", sync=False)
    def register_current_line(self):
        if self.is_active:
            line = self.nvim.current.line.strip()
            self.current_task = self.tasks[line] if line else None
            # self.current_task = self.tasks[self._get_current_line_index() - 1]

    @neovim.autocmd("InsertLeave", sync=False)
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

        # self.nvim.command(f"""echo "About to delete\n{task['content']}" """)
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

    @neovim.function("LoadTasks")
    def load_tasks(self, args):
        if self.is_active:
            self._clear_buffer()

            self.tasks = {}
            is_first_line = True

            for i, item in enumerate(self.todoist.state["items"]):
                if item["is_deleted"] or item["in_history"] or item["date_completed"]:
                    continue
                line = item["content"]
                if is_first_line:
                    self.nvim.current.line = line
                    is_first_line = False
                else:
                    if item["parent_id"]:
                        # This task has a parent task. It must be indented.
                        line = f"   {line}"
                    self.nvim.current.buffer.append(line)
                self.tasks[item["content"]] = item

                # self.nvim.current.line = api.state['items'][0]['content']
        else:
            self.nvim.command(
                'echo "The env var DEBUG_TODOIST is not set. Not doing anything."'
            )

    @neovim.function("DeleteTask")
    def delete_task(self, args):
        if self.is_active:
            line = self.nvim.current.line
            self._delete_task(line.strip())
            self.nvim.command("d")
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
        grand_father_id = parent_task['parent_id']
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
        self.nvim.api.buf_delete(0, {"force": True})

    def _get_current_line_index(self):
        return self.nvim.eval("line('.')")

    def _get_number_of_lines(self):
        return self.nvim.current.buffer.api.line_count()
