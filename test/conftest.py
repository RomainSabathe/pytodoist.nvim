import os
import json

import todoist
import pytest
import pynvim

from rplugin.python3.pytodoist import TodoistInterface, Plugin, CustomSection

pynvim.setup_logging("test")

os.environ["TODOIST_API_KEY"] = "test"


@pytest.fixture
def vim():
    child_argv = os.environ.get("NVIM_CHILD_ARGV")
    listen_address = os.environ.get("NVIM_LISTEN_ADDRESS")
    # Enable this for interactive debugging.
    # listen_address = "/tmp/nvim"
    if child_argv is None and listen_address is None:
        child_argv = '["nvim", "-u", "NONE", "--embed", "--headless"]'

    if child_argv is not None:
        editor = pynvim.attach("child", argv=json.loads(child_argv))
    else:
        assert listen_address is None or listen_address != ""
        editor = pynvim.attach("socket", path=listen_address)

    # Loading the bindings etc.
    editor.command(":source plugin/pytodoist.vim")
    return editor


@pytest.fixture
def todoist_api():
    if not os.environ.get("TODOIST_API_KEY"):
        raise ValueError("Can't find the TODOIST_API_KEY env var.")
    api = TodoistInterface(todoist.TodoistAPI(os.environ.get("TODOIST_API_KEY")))
    api.sync()
    return api


class FakeItemsManager(todoist.managers.items.ItemsManager):
    pass


class FakeApi(todoist.api.TodoistAPI):
    def __init__(self):
        self.queue = []

        self.state = dict()
        self.state["projects"] = [self._project_factory(i) for i in range(1, 4)]
        self.state["items"] = [
            *[self._task_factory(i, project_id=1) for i in range(1, 4)],
            *[self._task_factory(i, project_id=2) for i in range(4, 7)],
            *[self._task_factory(i, project_id=3) for i in range(7, 10)],
        ]
        self.state["labels"] = [self._label_factory(i) for i in range(1, 4)]

        # Assigning Tasks 1 and 7 with label `1`.
        self.state["items"][0]["labels"] = ["1"]
        self.state["items"][6]["labels"] = ["1"]

        # We make Project 1 the inbox project.
        self.state["projects"][0].data["inbox_project"] = True

        # In order to test that the projects get displayed in the correct order, we
        # alter the natural ordering.
        self.state["projects"] = self.state["projects"][::-1]
        # Setting `Project 2` as a child of `Project 1`.
        self.state["projects"][1]["parent_id"] = "1"
        self.state["projects"][1]["child_order"] = 1

        # We do the same for the tasks.
        self.state["items"] = self.state["items"][::-1]
        # Setting `Task 8` as a child of `Task 7`.
        self.state["items"][7]["parent_id"] = "6"
        self.state["items"][7]["child_order"] = 1

    def sync(self, commands=None):
        return commands

    def commit(self, raise_on_error=True):
        # Similar to the original implementation of `commit`, except that we take
        # care not to delete the queue.
        if len(self.queue) == 0:
            return
        ret = self.sync(commands=self.queue)
        return ret

    @property
    def items(self):
        return FakeItemsManager(api=self)

    def _task_factory(self, task_id: int, project_id: int):
        return todoist.models.Item(
            api=self,
            data={
                "content": f"Task {task_id}",
                "project_id": str(project_id),
                "id": str(task_id),
                "is_deleted": 0,
                "in_history": 0,
                "date_completed": None,
                "child_order": (task_id - 1) % 3,
                "parent_id": None,
                "labels": [],
            },
        )

    def _project_factory(self, project_id: int):
        return todoist.models.Project(
            api=self,
            data={
                "name": f"Project {project_id}",
                "id": str(project_id),
                "is_archived": 0,
                "is_deleted": 0,
                "color": project_id + 30,
                "parent_id": None,
                "child_order": project_id,
                "inbox_project": False,
            },
        )

    def _label_factory(self, label_id: int):
        return todoist.models.Label(
            api=self,
            data={
                "name": f"Label {label_id}",
                "id": str(label_id),
                "item_order": label_id,
                "is_deleted": 0,
                "is_favorite": 0,
            },
        )


@pytest.fixture
def custom_sections():
    return [
        CustomSection(
            name="Custom Section", filter_fn=lambda task: "Label 1" in task.labels
        )
    ]


@pytest.fixture
def plugin(vim, custom_sections):
    to_return = Plugin(vim)

    # Triggering the auto-cmds.
    to_return.insert_leave()
    to_return.text_changed()
    to_return.text_yank_post()
    to_return.save_buffer()

    to_return.todoist = TodoistInterface(FakeApi(), custom_sections=custom_sections)
    to_return.todoist.sync()
    return to_return
