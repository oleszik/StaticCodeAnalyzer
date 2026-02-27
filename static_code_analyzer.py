import os
import re
import sys
import ast
import io
import tokenize
from dataclasses import dataclass
from typing import Iterable


MAX_LINE_LENGTH = 79


@dataclass(frozen=True, order=True)
class ReportItem:
    file_path: str
    line_number: int
    code: str
    message: str


MESSAGES = {
    "S001": "Too long line",
    "S002": "Indentation is not a multiple of four",
    "S003": "Unnecessary semicolon",
    "S004": "At least two spaces required before inline comments",
    "S005": "TODO found",
    "S006": "More than two blank lines used before this line",
    "S007": "Too many spaces after '{kw}'",
    "S008": "Class name '{name}' should use CamelCase",
    "S009": "Function name '{name}' should use snake_case",
    "S010": "Argument name '{name}' should use snake_case",
    "S011": "Variable '{name}' in function should use snake_case",
    "S012": "Default argument value is mutable",
}

RE_TODO = re.compile(r"todo", re.IGNORECASE)

# Assumptions from the task: class/def are on one line like "class Name:" or "class Name(Base):"
RE_CLASS = re.compile(r"^(\s*)class(\s+)([A-Za-z_][A-Za-z0-9_]*)")
RE_DEF = re.compile(r"^(\s*)def(\s+)([A-Za-z_][A-Za-z0-9_]*)")


def split_code_and_comment(line: str) -> tuple[str, str, int]:
    """
    Returns (code_part, comment_part, comment_col).
    comment_col is -1 when there is no real comment token on this line.
    """
    try:
        tokens = tokenize.generate_tokens(io.StringIO(line).readline)
        for token in tokens:
            if token.type == tokenize.COMMENT:
                col = token.start[1]
                return line[:col].rstrip("\n"), line[col:].rstrip("\n"), col
    except tokenize.TokenError:
        # Fallback for malformed lines: keep behavior tolerant.
        pass
    return line.rstrip("\n"), "", -1


def is_camel_case(name: str) -> bool:
    # Minimal CamelCase check suitable for this project:
    # starts with uppercase, contains only letters/digits, no underscores.
    return bool(re.fullmatch(r"[A-Z][a-zA-Z0-9]*", name))


def is_snake_case(name: str) -> bool:
    # Allow leading/trailing underscores, require snake_case core.
    # Examples allowed: __init__, _print, do_magic, __fun__
    return bool(re.fullmatch(r"_*[a-z][a-z0-9_]*_*", name))


def check_s001(raw_line: str) -> str | None:
    if len(raw_line.rstrip("\n")) > MAX_LINE_LENGTH:
        return "S001"
    return None


def check_s002(raw_line: str) -> str | None:
    if not raw_line.strip():
        return None
    leading_spaces = len(raw_line) - len(raw_line.lstrip(" "))
    if leading_spaces % 4 != 0:
        return "S002"
    return None


def check_s003(code_part: str) -> str | None:
    if code_part.rstrip().endswith(";"):
        return "S003"
    return None


def check_s004(code_part: str, comment_col: int) -> str | None:
    if comment_col == -1:
        return None

    if code_part.strip() == "":
        return None  # full-line comment

    if not code_part.endswith("  "):
        return "S004"
    return None


def check_s005(comment_part: str) -> str | None:
    if comment_part and RE_TODO.search(comment_part):
        return "S005"
    return None


def check_s006(blank_lines_before: int, raw_line: str) -> str | None:
    if raw_line.strip() and blank_lines_before > 2:
        return "S006"
    return None


def check_s007_s008_s009(raw_line: str) -> list[tuple[str, dict]]:
    """
    Returns list of (code, format_kwargs) for S007/S008/S009 found on this line.
    """
    results: list[tuple[str, dict]] = []

    m_class = RE_CLASS.match(raw_line)
    if m_class:
        spaces = m_class.group(2)
        name = m_class.group(3)

        if len(spaces) > 1:
            results.append(("S007", {"kw": "class"}))
        if not is_camel_case(name):
            results.append(("S008", {"name": name}))
        return results

    m_def = RE_DEF.match(raw_line)
    if m_def:
        spaces = m_def.group(2)
        name = m_def.group(3)

        if len(spaces) > 1:
            results.append(("S007", {"kw": "def"}))
        if not is_snake_case(name):
            results.append(("S009", {"name": name}))
        return results

    return results


def find_issues_for_line(raw_line: str, blank_lines_before: int) -> list[tuple[str, dict]]:
    code_part, comment_part, comment_col = split_code_and_comment(raw_line)

    found: list[tuple[str, dict]] = []

    for code in (
        check_s001(raw_line),
        check_s002(raw_line),
        check_s006(blank_lines_before, raw_line),
        check_s003(code_part),
        check_s004(code_part, comment_col),
        check_s005(comment_part),
    ):
        if code is not None:
            found.append((code, {}))

    found.extend(check_s007_s008_s009(raw_line))

    # unique by code (only one report per code per line), then sort by code
    uniq: dict[str, dict] = {}
    for code, kwargs in found:
        uniq.setdefault(code, kwargs)

    return sorted(uniq.items(), key=lambda x: x[0])


def extract_assigned_names(target: ast.AST) -> list[str]:
    names: list[str] = []
    if isinstance(target, ast.Name):
        names.append(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            names.extend(extract_assigned_names(elt))
    return names


def walk_without_nested_scopes(nodes: list[ast.stmt]) -> Iterable[ast.AST]:
    skip_types = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
    stack: list[ast.AST] = list(reversed(nodes))
    while stack:
        node = stack.pop()
        yield node
        for child in ast.iter_child_nodes(node):
            if isinstance(child, skip_types):
                continue
            stack.append(child)


def analyze_ast_issues(file_path: str) -> list[ReportItem]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=file_path)
    except (SyntaxError, OSError, UnicodeDecodeError):
        return []

    items: list[ReportItem] = []
    function_types = (ast.FunctionDef, ast.AsyncFunctionDef)

    for node in ast.walk(tree):
        if not isinstance(node, function_types):
            continue

        arg_names: list[str] = []
        arg_names.extend(arg.arg for arg in node.args.posonlyargs)
        arg_names.extend(arg.arg for arg in node.args.args)
        arg_names.extend(arg.arg for arg in node.args.kwonlyargs)
        if node.args.vararg is not None:
            arg_names.append(node.args.vararg.arg)
        if node.args.kwarg is not None:
            arg_names.append(node.args.kwarg.arg)

        for arg_name in arg_names:
            if not is_snake_case(arg_name):
                items.append(
                    ReportItem(
                        file_path=file_path,
                        line_number=node.lineno,
                        code="S010",
                        message=MESSAGES["S010"].format(name=arg_name),
                    )
                )

        mutable_default = False
        defaults = list(node.args.defaults) + list(node.args.kw_defaults)
        for default in defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                mutable_default = True
                break
        if mutable_default:
            items.append(
                ReportItem(
                    file_path=file_path,
                    line_number=node.lineno,
                    code="S012",
                    message=MESSAGES["S012"],
                )
            )

        for inner in walk_without_nested_scopes(node.body):
            if isinstance(inner, ast.Assign):
                targets = inner.targets
            elif isinstance(inner, ast.AnnAssign):
                targets = [inner.target]
            elif isinstance(inner, ast.AugAssign):
                targets = [inner.target]
            else:
                continue

            for target in targets:
                for name in extract_assigned_names(target):
                    if not is_snake_case(name):
                        items.append(
                            ReportItem(
                                file_path=file_path,
                                line_number=inner.lineno,
                                code="S011",
                                message=MESSAGES["S011"].format(name=name),
                            )
                        )

    return items


def iter_python_files(path: str) -> Iterable[str]:
    if os.path.isfile(path):
        if path.endswith(".py"):
            yield path
        return

    for root, _dirs, files in os.walk(path):
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(root, name)


def analyze_file(file_path: str) -> list[ReportItem]:
    items: list[ReportItem] = []
    blank_lines_before = 0

    with open(file_path, "r", encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            issues = find_issues_for_line(raw_line, blank_lines_before)
            for code, fmt in issues:
                template = MESSAGES[code]
                message = template.format(**fmt) if fmt else template
                items.append(
                    ReportItem(
                        file_path=file_path,
                        line_number=line_number,
                        code=code,
                        message=message,
                    )
                )

            if raw_line.strip() == "":
                blank_lines_before += 1
            else:
                blank_lines_before = 0

    items.extend(analyze_ast_issues(file_path))
    return items


def main() -> None:
    if len(sys.argv) != 2:
        return

    input_path = sys.argv[1]
    all_items: list[ReportItem] = []

    for file_path in sorted(iter_python_files(input_path)):
        all_items.extend(analyze_file(file_path))

    for item in sorted(all_items):
        print(f"{item.file_path}: Line {item.line_number}: {item.code} {item.message}")


if __name__ == "__main__":
    main()
