import os

import todoist

from rplugin.python3.pytodoist import TasksWorld


def test_test():
    if not os.environ.get("TODOIST_API_KEY"):
        raise ValueError("Can't find the TODOIST_API_KEY env var.")
    api = todoist.TodoistAPI(os.environ.get("TODOIST_API_KEY"))
    api.sync()

    tasks = api.state["items"]

    task_world = TasksWorld(tasks)
    for task in task_world:
        print(str(task))
