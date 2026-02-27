# StaticCodeAnalyzer

Python static code analyzer for PEP8-style checks. Scans a file or project directory, reports sorted violations with code+line, and supports rule sets from basic formatting to AST-based checks: naming of functions/args/local vars and mutable default arguments. Useful for linting practice and code quality automation.

## Features

- **Line-based checks**: Detects long lines, indentation issues, unnecessary semicolons, comment formatting, TODOs, excessive blank lines, and spacing after `class`/`def` keywords.
- **Naming conventions**: Enforces CamelCase for classes, snake_case for functions, arguments, and local variables.
- **Mutable default arguments**: Warns if a function uses mutable types (list, dict, set) as default arguments.
- **Recursive directory scan**: Analyzes all `.py` files in a directory tree.
- **AST-based analysis**: Uses Python's `ast` module for deep inspection of function arguments and variable assignments.

## Rules Implemented

| Code  | Description |
|-------|-------------|
| S001  | Too long line (>79 chars) |
| S002  | Indentation is not a multiple of four |
| S003  | Unnecessary semicolon |
| S004  | At least two spaces required before inline comments |
| S005  | TODO found in comment |
| S006  | More than two blank lines used before this line |
| S007  | Too many spaces after 'class' or 'def' keyword |
| S008  | Class name should use CamelCase |
| S009  | Function name should use snake_case |
| S010  | Argument name should use snake_case |
| S011  | Variable in function should use snake_case |
| S012  | Default argument value is mutable |

## Usage

```bash
python static_code_analyzer.py <file_or_directory>
```

- Pass a single Python file or a directory to recursively analyze all `.py` files.
- Output is sorted by file, line, and rule code.

## Example Output

```
example.py: Line 10: S001 Too long line
example.py: Line 15: S008 Class name 'my_class' should use CamelCase
```

## Implementation Overview

- **Line checks**: Uses regex and tokenization to split code and comments, then applies formatting rules.
- **AST checks**: Parses files with `ast` to inspect function definitions, argument names, variable assignments, and default values.
- **ReportItem**: Each violation is stored as a `ReportItem` dataclass with file, line, code, and message.
- **Extensible**: New rules can be added by extending the check functions and message dictionary.

## File Structure

- `static_code_analyzer.py`: Main analyzer script with all logic and rules.
- `README.md`: This documentation.

## Requirements

- Python 3.10+

## License

MIT License
