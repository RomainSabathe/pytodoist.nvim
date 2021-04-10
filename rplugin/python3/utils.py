import re
import subprocess
from pathlib import Path


class AddDiff:
    def __init__(self, index, new_lines):
        self.index = index
        self.new_lines = new_lines


def get_diffs(lhs, rhs):
    raw_diff = get_raw_diff(lhs, rhs)
    return interpret_raw_diff(raw_diff)


def get_raw_diff(lhs, rhs):
    # TODO: that's dirty. Ideally we should pipe directly to `diff`.
    path_lhs = Path("/tmp/lhs")
    path_lhs.write_text(lhs)

    path_rhs = Path("/tmp/rhs")
    path_rhs.write_text(rhs)

    diff_output = subprocess.run(
        ["diff", "-e", str(path_lhs), str(path_rhs)], capture_output=True
    ).stdout.decode()[:-1]  # Trimming the last "\n"

    return diff_output


def interpret_raw_diff(diff):
    to_return = []

    diff_lines = diff.split("\n")
    k = 0
    add_regex = re.compile(r"^(?P<start>\d+)a(?P<from>\d+)(,(?P<to>\d+))?$")
    add_regex = re.compile(r"^(?P<index>\d+)a$")
    while k < len(diff_lines):
        line = diff_lines[k]
        if "a" in line:
            # 'Add'  mode.
            index = int(add_regex.match(line).group("index"))
            new_lines = []
            k += 1
            while diff_lines[k] != ".":
                new_lines.append(diff_lines[k])
                k += 1
            to_return.append(AddDiff(index, new_lines))
            k += 1

    return to_return
