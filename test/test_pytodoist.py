import os

import pytest
import todoist
import pandas as pd

from rplugin.python3.pytodoist import TasksWorld, World, AddDiff, get_diffs, interpret_raw_diff


def test_initialize_task_world(todoist_api):
    tasks = todoist_api.state["items"]

    task_world = TasksWorld(tasks)
    for task in task_world:
        print(str(task))


def test_assign_project_id_to_tasks(todoist_api):
    tasks = pd.DataFrame([item.data for item in todoist_api.state["items"]])
    projects = pd.DataFrame([project.data for project in todoist_api.state["projects"]])
    tasks = tasks.merge(
        projects.set_index("id").rename(columns={"name": "project_name"})[
            ["project_name"]
        ],
        left_on="project_id",
        right_index=True,
        suffixes=("", "_project"),
    )


def test_filter_tasks(todoist_api):
    tasks = todoist_api.state["items"]
    query = "#perso and not @someday and not due"
    query = "#pro and not @someday and @documentation"
    query = "#pro and no label"

    import re
    from copy import deepcopy

    tasks = deepcopy(tasks)

    # Fetching the projects.
    pattern = r"#(?P<project_name>\w+)"
    for project_name in re.findall(pattern, query):
        project_id = [
            project["id"]
            for project in todoist_api.state["projects"]
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
            for label in todoist_api.state["labels"]
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


def test_initialize_world(todoist_api):
    world = World(todoist_api)
    for line in world:
        assert "\n" not in line  # we can't add lines that have "\n" to the buffer.
    print(world.projects)


def test_world_iterprint(todoist_api):
    world = World(todoist_api)
    for line in world.iterprint():
        print(line)


def test_add_task():
    before = """
Project 1
=========
Task 1
Task 2

Project 2
=========
Task 3
Task 4

Project 3
=========
Task 5
Task 6
"""
    before = before[1:-1]

    after = """
Project 1
=========
Task 1
Task 2

Project 2
=========
Task 3
Task 7
Task 4

Project 3
=========
Task 5
Task 6
"""
    after = after[1:-1]

    diffs = get_diffs(before, after)
    assert len(diffs) == 1

    diff = diffs[0]
    assert isinstance(diff, AddDiff)
    assert diff.index == 8
    assert len(diff.new_lines) == 1
    assert diff.new_lines[0] == "Task 7"

def test_dumb():
    import subprocess
    from pathlib import Path
    path_lhs = Path("/tmp/lhs")
    path_rhs = Path("/tmp/rhs")
    if path_lhs.exists():
        path_lhs.unlink()
    if path_rhs.exists():
        path_rhs.unlink()

    diff_output = subprocess.run(
        ["diff", "-e", str(path_lhs), str(path_rhs)], capture_output=True
    ).stdout.decode()[
        :-1
    ]  # Trimming the last "\n"

    print(interpret_raw_diff(diff_output))


@pytest.fixture
def todoist_api():
    if not os.environ.get("TODOIST_API_KEY"):
        raise ValueError("Can't find the TODOIST_API_KEY env var.")
    api = todoist.TodoistAPI(os.environ.get("TODOIST_API_KEY"))
    api.sync()
    return api
