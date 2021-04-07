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


def test_filter_tasks():
    if not os.environ.get("TODOIST_API_KEY"):
        raise ValueError("Can't find the TODOIST_API_KEY env var.")
    api = todoist.TodoistAPI(os.environ.get("TODOIST_API_KEY"))
    api.sync()

    tasks = api.state["items"]
    query = "#perso and not @someday and not due"
    query = "#pro and not @someday and @documentation"

    import re
    from copy import deepcopy

    tasks = deepcopy(tasks)

    # Fetching the projects.
    pattern = r"#(?P<project_name>\w+)"
    for project_name in re.findall(pattern, query):
        project_id = [
            project["id"]
            for project in api.state["projects"]
            if project["name"].lower() == project_name
        ][0]
        idx_to_delete = []
        for i, task in enumerate(tasks):
            if task["project_id"] != project_id:
                idx_to_delete.append(i)
        for idx in idx_to_delete[::-1]:
            del tasks[idx]

    # Fetching the labels.
    pattern = r"(not)? @(?P<label_name>\w+)"
    for (is_negation, label_name) in re.findall(pattern, query):
        label_id = [
            label["id"]
            for label in api.state["labels"]
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

    task_world = TasksWorld(tasks)
    for task in task_world:
        print(str(task))
