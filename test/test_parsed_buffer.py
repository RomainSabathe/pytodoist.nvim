from rplugin.python3.pytodoist import ParsedBuffer


def test_init():
    from pathlib import Path

    lines = Path("/tmp/todoist").read_text().split("\n")
    parsed_buffer = ParsedBuffer(lines)
    result = parsed_buffer.parse_lines()


def test_diff(todoist_api):
    from pathlib import Path

    # lines_before = Path("/tmp/todoist_before").read_text().split("\n")
    lines_before = Path("/tmp/lhs").read_text().split("\n")
    buffer_before = ParsedBuffer(lines_before, todoist_api)

    # lines_after = Path("/tmp/todoist_after").read_text().split("\n")
    lines_after = Path("/tmp/rhs").read_text().split("\n")
    buffer_after = ParsedBuffer(lines_after)

    buffer_before.compare_with(buffer_after)


def test_interface(todoist_api):
    for item in todoist_api:
        pass


def test_move_task(plugin, vim):
    # Moving `Task 2` to `Project 2`.
    # vim.current.buffer[:] = [
    #     "Project 1",
    #     "=========",
    #     "Task 1",
    #     "Task 2",  # Line 4
    #     "Task 3",
    #     "",
    #     "Project 2",
    #     "=========",
    #     "Task 4",
    #     "Task 5",
    #     "Task 6",  # Line 11
    #     "",
    #     "Project 3",
    #     "=========",
    #     "Task 7",
    #     "Task 8",
    #     "Task 9",
    #     "",
    # ]

    # plugin._clear_buffer()
    # plugin.todoist.sync()
    # for i, item in enumerate(plugin.todoist):
    #     item = str(item)
    #     if i == 0:
    #         plugin.nvim.current.line = item
    #     else:
    #         plugin.nvim.current.buffer.append(item)
    # import ipdb; ipdb.set_trace()
    # pass
    la = plugin.load_tasks(args=[])
    import ipdb; ipdb.set_trace()
    pass


    parsed_buffer = ParsedBuffer(vim.current.buffer[:])
    plugin.parsed_buffer = parsed_buffer

    # Setting position to `Task 2`, which is located at line 4.
    line_index = 4
    vim.api.command(f"call setpos('.', [1, {line_index}, 1, 0])")
    # Moving this line to `Project 2`.
    plugin.move_task(args=["Project 2"], _range=[line_index, line_index])

    import ipdb

    ipdb.set_trace()
    pass
