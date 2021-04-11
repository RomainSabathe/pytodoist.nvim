import os
import pytest
import todoist

from rplugin.python3.pytodoist import ParsedBuffer, TodoistInterface

def test_init():
    from pathlib import Path
    lines = Path("/tmp/todoist").read_text().split("\n")
    parsed_buffer = ParsedBuffer(lines)
    result = parsed_buffer.parse_lines()

def test_diff(todoist_api):
    from pathlib import Path
    lines_before = Path("/tmp/todoist_before").read_text().split("\n")
    buffer_before = ParsedBuffer(lines_before, todoist_api)

    lines_after = Path("/tmp/todoist_after").read_text().split("\n")
    buffer_after = ParsedBuffer(lines_after)

    buffer_before.compare_with(buffer_after)

def test_interface(todoist_api):
    for item in todoist_api:
        pass

@pytest.fixture
def todoist_api():
    if not os.environ.get("TODOIST_API_KEY"):
        raise ValueError("Can't find the TODOIST_API_KEY env var.")
    api = TodoistInterface(todoist.TodoistAPI(os.environ.get("TODOIST_API_KEY")))
    api.sync()
    return api
