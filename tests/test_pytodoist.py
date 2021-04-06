import os

import todoist
import pandas as pd

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


def test_test2():
    if not os.environ.get("TODOIST_API_KEY"):
        raise ValueError("Can't find the TODOIST_API_KEY env var.")
    api = todoist.TodoistAPI(os.environ.get("TODOIST_API_KEY"))
    api.sync()

    tasks = pd.DataFrame([item.data for item in api.state["items"]])
    projects = pd.DataFrame([project.data for project in api.state["projects"]])
    tasks = tasks.merge(
        projects.set_index("id").rename(columns={"name": "project_name"})[
            ["project_name"]
        ],
        left_on="project_id",
        right_index=True,
        suffixes=("", "_project"),
    )
