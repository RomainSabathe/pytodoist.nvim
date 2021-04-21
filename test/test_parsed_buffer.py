from rplugin.python3.pytodoist import ParsedBuffer, Project, Task, ProjectUnderline


# def test_init():
#     from pathlib import Path

#     lines = Path("/tmp/todoist").read_text().split("\n")
#     parsed_buffer = ParsedBuffer(lines)
#     result = parsed_buffer.parse_lines()


# def test_diff(todoist_api):
#     from pathlib import Path

#     # lines_before = Path("/tmp/todoist_before").read_text().split("\n")
#     lines_before = Path("/tmp/lhs").read_text().split("\n")
#     buffer_before = ParsedBuffer(lines_before, todoist_api)

#     # lines_after = Path("/tmp/todoist_after").read_text().split("\n")
#     lines_after = Path("/tmp/rhs").read_text().split("\n")
#     buffer_after = ParsedBuffer(lines_after)

#     buffer_before.compare_with(buffer_after)


def test_interface(todoist_api):
    for item in todoist_api:
        pass


def test_load_tasks(plugin, vim):
    plugin.load_tasks(args=[])

    assert vim.current.buffer[:] == [
        "Project 1",
        "=========",
        "[ ] Task 1",
        "[ ] Task 2",
        "[ ] Task 3",
        "",
        "Project 2",
        "=========",
        "[ ] Task 4",
        "[ ] Task 5",
        "[ ] Task 6",
        "",
        "Project 3",
        "=========",
        "[ ] Task 7",
        "[ ] Task 8",
        "[ ] Task 9",
        "",
    ]


def test_move_task_1(plugin, vim):
    """Move a single task downwards in the buffer."""
    # Moving `Task 2` to `Project 2`.
    plugin.load_tasks(args=[])

    # Setting position to `Task 2`, which is located at line 4.
    line_index = 4
    vim.api.command(f"call setpos('.', [1, {line_index}, 1, 0])")
    # Moving this line to `Project 2`.
    plugin.move_task(args=["Project 2"], _range=[line_index, line_index])

    # Checking the task has been moved.
    assert vim.current.buffer[:] == [
        "Project 1",
        "=========",
        "[ ] Task 1",
        "[ ] Task 3",
        "",
        "Project 2",
        "=========",
        "[ ] Task 4",
        "[ ] Task 5",
        "[ ] Task 6",
        "[ ] Task 2",
        "",
        "Project 3",
        "=========",
        "[ ] Task 7",
        "[ ] Task 8",
        "[ ] Task 9",
        "",
    ]

    # In addition, the cursor should be on `Task 3`.
    # As usual, the -1 handles the difference 0-based indexing and 1-based indexing.
    assert vim.current.buffer[plugin._get_current_line_index() - 1] == "[ ] Task 3"


def test_move_task_2(plugin, vim):
    """Move a single task downwards in the buffer, to the last project."""
    # Moving `Task 2` to `Project 3` (which is the last project).
    plugin.load_tasks(args=[])

    # Setting position to `Task 2`, which is located at line 4.
    line_index = 4
    vim.api.command(f"call setpos('.', [1, {line_index}, 1, 0])")
    # Moving this line to `Project 2`.
    plugin.move_task(args=["Project 3"], _range=[line_index, line_index])

    # Checking the task has been moved.
    assert vim.current.buffer[:] == [
        "Project 1",
        "=========",
        "[ ] Task 1",
        "[ ] Task 3",
        "",
        "Project 2",
        "=========",
        "[ ] Task 4",
        "[ ] Task 5",
        "[ ] Task 6",
        "",
        "Project 3",
        "=========",
        "[ ] Task 7",
        "[ ] Task 8",
        "[ ] Task 9",
        "[ ] Task 2",
        "",
    ]

    # In addition, the cursor should be on `Task 3`.
    # As usual, the -1 handles the difference 0-based indexing and 1-based indexing.
    assert vim.current.buffer[plugin._get_current_line_index() - 1] == "[ ] Task 3"


def test_move_task_3(plugin, vim):
    """Move a single task upwards in the buffer."""
    # Moving `Task 5` to `Project 1`.
    plugin.load_tasks(args=[])

    # Setting position to `Task 5`, which is located at line 10.
    line_index = 10
    vim.api.command(f"call setpos('.', [1, {line_index}, 1, 0])")
    # Moving this line to `Project 1`.
    plugin.move_task(args=["Project 1"], _range=[line_index, line_index])

    # Checking the task has been moved.
    assert vim.current.buffer[:] == [
        "Project 1",
        "=========",
        "[ ] Task 1",
        "[ ] Task 2",
        "[ ] Task 3",
        "[ ] Task 5",
        "",
        "Project 2",
        "=========",
        "[ ] Task 4",
        "[ ] Task 6",
        "",
        "Project 3",
        "=========",
        "[ ] Task 7",
        "[ ] Task 8",
        "[ ] Task 9",
        "",
    ]

    # In addition, the cursor should be on `Task 6`.
    # As usual, the -1 handles the difference 0-based indexing and 1-based indexing.
    assert vim.current.buffer[plugin._get_current_line_index() - 1] == "[ ] Task 6"


def test_move_task_4(plugin, vim):
    """Move multiple tasks downwards in the buffer."""
    # Moving `Task 2` and `Task 3` to `Project 2`.
    plugin.load_tasks(args=[])

    # Setting position to `Task 2`, which is located at line 4.
    line_index = 4
    vim.api.command(f"call setpos('.', [1, {line_index}, 1, 0])")
    # We move `Task 2` and `Task 3` to `Project 2`.
    plugin.move_task(args=["Project 2"], _range=[line_index, line_index + 1])

    # Checking the task has been moved.
    assert vim.current.buffer[:] == [
        "Project 1",
        "=========",
        "[ ] Task 1",
        "",
        "Project 2",
        "=========",
        "[ ] Task 4",
        "[ ] Task 5",
        "[ ] Task 6",
        "[ ] Task 2",
        "[ ] Task 3",
        "",
        "Project 3",
        "=========",
        "[ ] Task 7",
        "[ ] Task 8",
        "[ ] Task 9",
        "",
    ]

    # In addition, the cursor should be on ``.
    # As usual, the -1 handles the difference 0-based indexing and 1-based indexing.
    assert vim.current.buffer[plugin._get_current_line_index() - 1] == ""


def test_move_task_5(plugin, vim):
    """Move multiple tasks upwards in the buffer."""
    # Moving `Task 8` and `Task 9` to `Project 1`.
    plugin.load_tasks(args=[])

    # Setting position to `Task 8`, which is located at line 16.
    line_index = 16
    vim.api.command(f"call setpos('.', [1, {line_index}, 1, 0])")
    # And moving upwards.
    plugin.move_task(args=["Project 1"], _range=[line_index, line_index + 1])

    # Checking the task has been moved.
    assert vim.current.buffer[:] == [
        "Project 1",
        "=========",
        "[ ] Task 1",
        "[ ] Task 2",
        "[ ] Task 3",
        "[ ] Task 8",
        "[ ] Task 9",
        "",
        "Project 2",
        "=========",
        "[ ] Task 4",
        "[ ] Task 5",
        "[ ] Task 6",
        "",
        "Project 3",
        "=========",
        "[ ] Task 7",
        "",
    ]

    # In addition, the cursor should be on ``.
    # As usual, the -1 handles the difference 0-based indexing and 1-based indexing.
    assert vim.current.buffer[plugin._get_current_line_index() - 1] == ""


def test_complete_tasks(plugin, vim):
    plugin.load_tasks(args=[])

    # Setting position to `Task 5`.
    line_index = 10
    vim.api.command(f"call setpos('.', [1, {line_index}, 1, 0])")

    plugin.complete_task(args=[])

    assert vim.current.buffer[:] == [
        "Project 1",
        "=========",
        "[ ] Task 1",
        "[ ] Task 2",
        "[ ] Task 3",
        "",
        "Project 2",
        "=========",
        "[ ] Task 4",
        "[ ] Task 6",
        "",
        "Project 3",
        "=========",
        "[ ] Task 7",
        "[ ] Task 8",
        "[ ] Task 9",
        "",
    ]


def test_load_tasks_when_using_multiple_windows(plugin, vim):
    # Creating a first window and populating it with text.
    assert vim.current.window.cursor == [1, 0]
    vim.command("normal iThis text is not in the Todoist buffer")
    assert vim.current.buffer[:] == ["This text is not in the Todoist buffer"]
    # By default, `g:hidden` is set to "hide" which means that opening a new buffer
    # can be done only if we save the changes here. Let's do this and load the tasks
    # only after.
    tmp_name = vim.eval("resolve(tempname())")
    vim.current.buffer.name = tmp_name
    vim.command("w")

    # Opening up the Todoist buffer.
    plugin.load_tasks(args=[])

    # We should now have two buffers, and we should be located on the Todoist buffer.
    assert len(vim.buffers) == 2
    assert vim.current.buffer[:] == [
        "Project 1",
        "=========",
        "[ ] Task 1",
        "[ ] Task 2",
        "[ ] Task 3",
        "",
        "Project 2",
        "=========",
        "[ ] Task 4",
        "[ ] Task 5",
        "[ ] Task 6",
        "",
        "Project 3",
        "=========",
        "[ ] Task 7",
        "[ ] Task 8",
        "[ ] Task 9",
        "",
    ]
    assert vim.current.buffer.number == 2
    # Checking that the content of the tmp buffer hasn't changed.
    vim.command("1b")
    assert vim.current.buffer[:] == ["This text is not in the Todoist buffer"]

    # Now splitting in 2 windows. On the left, we'll have the tmp buffer, and on the
    # right we'll have todoist.
    vim.command("vsplit")
    assert len(vim.windows) == 2
    # The tmp buffer is shown on left and right windows. Now Todoist on the right window.
    vim.current.window = vim.windows[1]
    vim.command("2b")

    # We place the cursor on `Project 2` (line 7) and load the tasks again.
    vim.current.window.cursor = [7, 0]
    assert vim.current.buffer[plugin._get_current_line_index() - 1] == "Project 2"

    # We move once last time to the tmp buffer.
    vim.command("1b")

    # Now reloading the tasks.
    plugin.load_tasks(args=[])

    # We still should have 2 buffers.
    assert len(vim.buffers) == 2

    # We still should have 2 windows.
    assert len(vim.windows) == 2

    # The current buffer should have been changed, and now be set to the Todoist one.
    assert vim.current.buffer.number == 2

    # The content of the buffer should not have changed.
    assert vim.current.buffer[:] == [
        "Project 1",
        "=========",
        "[ ] Task 1",
        "[ ] Task 2",
        "[ ] Task 3",
        "",
        "Project 2",
        "=========",
        "[ ] Task 4",
        "[ ] Task 5",
        "[ ] Task 6",
        "",
        "Project 3",
        "=========",
        "[ ] Task 7",
        "[ ] Task 8",
        "[ ] Task 9",
        "",
    ]

    # The cursor should have been set at the same position.
    assert vim.current.buffer[plugin._get_current_line_index() - 1] == "Project 2"

    # The tmp buffer should also be intact.
    vim.command("1b")
    assert vim.current.buffer[:] == ["This text is not in the Todoist buffer"]


def test_parsed_buffer_2(plugin, vim):
    plugin.load_tasks(args=[])

    assert isinstance(plugin.parsed_buffer[0], Project)
    assert plugin.parsed_buffer[0].name == "Project 1"
    assert plugin.parsed_buffer[0].id == "1"

    assert isinstance(plugin.parsed_buffer[1], ProjectUnderline)

    assert isinstance(plugin.parsed_buffer[2], Task)
    assert plugin.parsed_buffer[2].content == "Task 1"
    assert plugin.parsed_buffer[2].id == "1"

    assert isinstance(plugin.parsed_buffer[3], Task)
    assert plugin.parsed_buffer[3].content == "Task 2"
    assert plugin.parsed_buffer[3].id == "2"


def test_adding_new_tasks_with_o_adds_a_prefix(plugin, vim):
    plugin.load_tasks(args=[])

    # Placing the cursor at `[ ] Task 2`.
    vim.command("call setpos('.', [1, 4, 1, 0])")
    assert vim.current.buffer[plugin._get_current_line_index() - 1] == "[ ] Task 2"

    # Inserting a new task below.
    vim.command("normal oThis is a new task")

    # The prefix `[ ]` has been automatically added.
    assert (
        vim.current.buffer[plugin._get_current_line_index() - 1]
        == "[ ] This is a new task"
    )

    assert vim.current.buffer[:] == [
        "Project 1",
        "=========",
        "[ ] Task 1",
        "[ ] Task 2",
        "[ ] This is a new task",
        "[ ] Task 3",
        "",
        "Project 2",
        "=========",
        "[ ] Task 4",
        "[ ] Task 5",
        "[ ] Task 6",
        "",
        "Project 3",
        "=========",
        "[ ] Task 7",
        "[ ] Task 8",
        "[ ] Task 9",
        "",
    ]

    # Now placing the cursor at `[ ] Task 8`
    vim.command("call setpos('.', [1, 17, 1, 0])")
    assert vim.current.buffer[plugin._get_current_line_index() - 1] == "[ ] Task 8"

    # Inserting a task above.
    vim.command("normal OThis is another task")

    assert vim.current.buffer[:] == [
        "Project 1",
        "=========",
        "[ ] Task 1",
        "[ ] Task 2",
        "[ ] This is a new task",
        "[ ] Task 3",
        "",
        "Project 2",
        "=========",
        "[ ] Task 4",
        "[ ] Task 5",
        "[ ] Task 6",
        "",
        "Project 3",
        "=========",
        "[ ] Task 7",
        "[ ] This is another task",
        "[ ] Task 8",
        "[ ] Task 9",
        "",
    ]

def test_parsed_buffer_with_complete_tasks(vim, plugin):
    plugin.load_tasks(args=[])

    assert isinstance(plugin.parsed_buffer[2], Task)
    assert plugin.parsed_buffer[2].content == "Task 1"
    assert not plugin.parsed_buffer[2].is_complete

    # We fictionaly complete `Task 1` with X.
    vim.current.buffer[2] = "[X] Task 1"

    plugin._refresh_parsed_buffer()
    assert isinstance(plugin.parsed_buffer[2], Task)
    assert plugin.parsed_buffer[2].content == "Task 1"
    assert plugin.parsed_buffer[2].is_complete

    # We fictionaly complete `Task 3` with x.
    vim.current.buffer[4] = "[x] Task 3"

    plugin._refresh_parsed_buffer()
    assert isinstance(plugin.parsed_buffer[4], Task)
    assert plugin.parsed_buffer[4].content == "Task 3"
    assert plugin.parsed_buffer[4].is_complete

    # Un-doing the task completion for `Task 1`.
    vim.current.buffer[2] = "[ ] Task 1"

    plugin._refresh_parsed_buffer()
    assert isinstance(plugin.parsed_buffer[2], Task)
    assert plugin.parsed_buffer[2].content == "Task 1"
    assert not plugin.parsed_buffer[2].is_complete

def test_adding_new_tasks_without_o_adds_a_prefix(plugin, vim):
    plugin.load_tasks(args=[])

    # Placing the cursor at `[ ] Task 2`.
    vim.command("call setpos('.', [1, 4, 1, 0])")
    assert vim.current.buffer[plugin._get_current_line_index() - 1] == "[ ] Task 2"

    # Inserting two new tasks below.
    # The first task will automatically have the prefix `[ ]` thanks to the remapping
    # of `o`.
    # The other task, however, is created without using `o`.
    vim.command("normal oThis is a new task\nThis is another task")

    plugin._refresh_parsed_buffer()

    # The prefix `[ ]` has been automatically added.
    assert (
        vim.current.buffer[plugin._get_current_line_index() - 1]
        == "[ ] This is another task"
    )

    assert vim.current.buffer[:] == [
        "Project 1",
        "=========",
        "[ ] Task 1",
        "[ ] Task 2",
        "[ ] This is a new task",
        "[ ] This is another task",
        "[ ] Task 3",
        "",
        "Project 2",
        "=========",
        "[ ] Task 4",
        "[ ] Task 5",
        "[ ] Task 6",
        "",
        "Project 3",
        "=========",
        "[ ] Task 7",
        "[ ] Task 8",
        "[ ] Task 9",
        "",
    ]

    # We also check that manually writing '[ ]' doesn't cause it to appear
    # twice (coming from the user and coming from the script).
    vim.command("normal oTask 10\n[ ] Task 11")

    plugin._refresh_parsed_buffer()

    assert (
        vim.current.buffer[plugin._get_current_line_index() - 1]
        == "[ ] Task 11"
    )

    assert vim.current.buffer[:] == [
        "Project 1",
        "=========",
        "[ ] Task 1",
        "[ ] Task 2",
        "[ ] This is a new task",
        "[ ] This is another task",
        "[ ] Task 10",
        "[ ] Task 11",
        "[ ] Task 3",
        "",
        "Project 2",
        "=========",
        "[ ] Task 4",
        "[ ] Task 5",
        "[ ] Task 6",
        "",
        "Project 3",
        "=========",
        "[ ] Task 7",
        "[ ] Task 8",
        "[ ] Task 9",
        "",
    ]

def test_add_task(plugin, vim):
    plugin.load_tasks(args=[])

    # Placing the cursor at `[ ] Task 2`.
    # We add a new task called `Task 10`.
    vim.command("call setpos('.', [1, 4, 1, 0])")
    vim.command("normal oTask 10")
    plugin.save_buffer()

    # We expect the following properties:
    # 1. We added a task (for Todoist, this is an 'item_add' event).
    # 2. The task has content `Task 10`.
    # 3. It is located within the `Project 1` (which has id "1").

    assert isinstance(plugin.todoist.api.queue, list)
    assert len(plugin.todoist.api.queue) == 1

    item = plugin.todoist.api.queue[0]
    assert isinstance(item, dict)

    assert item["type"] == "item_add"
    assert isinstance(item["args"], dict)
    assert item["args"]["content"] == "Task 10"
    assert item["args"]["project_id"] == "1"
    assert item["args"]["child_order"] == 99

def test_delete_task(plugin, vim):
    plugin.load_tasks(args=[])

    # Placing the cursor at `[ ] Task 2`.
    # We delete this task.
    vim.command("call setpos('.', [1, 4, 1, 0])")
    vim.command("normal dd")
    plugin.save_buffer()

    assert isinstance(plugin.todoist.api.queue, list)
    assert len(plugin.todoist.api.queue) == 1

    item = plugin.todoist.api.queue[0]
    assert isinstance(item, dict)

    assert item["type"] == "item_delete"
    assert isinstance(item["args"], dict)
    assert item["args"]["id"] == "2"

def test_edit_task(plugin, vim):
    plugin.load_tasks(args=[])

    # Placing the cursor at `[ ] Task 2`.
    # We replace this task with "Task 10"
    vim.command("call setpos('.', [1, 4, 1, 0])")
    vim.command("normal ccTask 10")
    plugin.save_buffer()

    # The prefix [ ] should have been added.
    assert vim.current.buffer[plugin._get_current_line_index() - 1] == "[ ] Task 10"

    assert isinstance(plugin.todoist.api.queue, list)
    assert len(plugin.todoist.api.queue) == 1

    item = plugin.todoist.api.queue[0]
    assert isinstance(item, dict)

    assert item["type"] == "item_update"
    assert isinstance(item["args"], dict)
    assert item["args"]["id"] == "2"
    assert item["args"]["content"] == "Task 10"
