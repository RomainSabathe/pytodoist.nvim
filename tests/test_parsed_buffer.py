from rplugin.python3.pytodoist import ParsedBuffer

def test_init():
    from pathlib import Path
    lines = Path("/tmp/todoist").read_text().split("\n")
    parsed_buffer = ParsedBuffer(lines)
    result = parsed_buffer.parse_lines()

    import ipdb; ipdb.set_trace()
    pass
