import os
import json

import todoist
import pytest
import pynvim

from rplugin.python3.pytodoist import TodoistInterface, Plugin

pynvim.setup_logging("test")

os.environ["TODOIST_API_KEY"] = "test"


@pytest.fixture
def vim():
    child_argv = os.environ.get("NVIM_CHILD_ARGV")
    listen_address = os.environ.get("NVIM_LISTEN_ADDRESS")
    listen_address = "/tmp/nvim"
    if child_argv is None and listen_address is None:
        child_argv = '["nvim", "-u", "NONE", "--embed", "--headless"]'

    if child_argv is not None:
        editor = pynvim.attach("child", argv=json.loads(child_argv))
    else:
        assert listen_address is None or listen_address != ""
        editor = pynvim.attach("socket", path=listen_address)

    return editor


@pytest.fixture
def todoist_api():
    if not os.environ.get("TODOIST_API_KEY"):
        raise ValueError("Can't find the TODOIST_API_KEY env var.")
    api = TodoistInterface(todoist.TodoistAPI(os.environ.get("TODOIST_API_KEY")))
    api.sync()
    return api


class FakeApi(todoist.api.TodoistAPI):
    def __init__(self):
        self.state = dict()
        self.state["projects"] = [self._project_factory(i) for i in range(1, 4)]
        self.state["items"] = [
            *[self._task_factory(i, project_id=1) for i in range(1, 4)],
            *[self._task_factory(i, project_id=2) for i in range(4, 7)],
            *[self._task_factory(i, project_id=3) for i in range(7, 10)],
        ]

    def sync(self):
        pass

    def _task_factory(self, task_id: int, project_id: int):
        return {
            "content": f"Task {task_id}",
            "project_id": f"{project_id}",
            "id": str(task_id),
            "is_deleted": 0,
            "in_history": 0,
            "date_completed": None,
            "child_order": (task_id - 1) % 3,
        }

    def _project_factory(self, project_id: int):
        return {
            "name": f"Project {project_id}",
            "id": f"{project_id}",
            "is_archived": 0,
            "is_deleted": 0,
            "color": project_id + 30,
        }


@pytest.fixture
def plugin(vim):
    to_return = Plugin(vim)
    to_return.todoist = TodoistInterface(FakeApi())
    to_return.todoist.sync()
    return to_return
