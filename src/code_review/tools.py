"""Read-only LangChain tools bound to one immutable source snapshot."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from langchain_core.tools import StructuredTool

from .models import ReviewRequest, SourceFile

SUPPORTED_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".rb", ".php",
    ".c", ".cpp", ".h", ".cs", ".sh", ".sql", ".swift", ".kt", ".scala",
}


def numbered(file: SourceFile, start: int = 1, end: int | None = None) -> str:
    lines = file.content.splitlines()
    end = min(end or len(lines), len(lines))
    return "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, end + 1))


def python_analysis(files: list[SourceFile]) -> dict:
    """AST-only heuristics: observations require specialist interpretation."""
    output: dict = {"files": [], "scope": "AST inspection only; source was never executed."}
    for file in files:
        if not file.path.endswith(".py"):
            continue
        entry: dict = {"file": file.path, "functions": [], "observations": []}
        output["files"].append(entry)
        try:
            tree = ast.parse(file.content, filename=file.path)
        except (SyntaxError, ValueError, RecursionError) as exc:
            entry["parse_error"] = {"line": getattr(exc, "lineno", 1), "kind": type(exc).__name__}
            continue
        aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                aliases.update({a.asname or a.name: a.name for a in node.names})
            elif isinstance(node, ast.ImportFrom):
                aliases.update({a.asname or a.name: f"{node.module}.{a.name}" for a in node.names})

        def call_name(node: ast.AST) -> str:
            if isinstance(node, ast.Name):
                return aliases.get(node.id, node.id)
            if isinstance(node, ast.Attribute):
                return f"{call_name(node.value)}.{node.attr}"
            return ""

        def observe(node: ast.AST, kind: str, detail: str) -> None:
            if len(entry["observations"]) < 80:
                entry["observations"].append({"line": node.lineno, "kind": kind, "detail": detail})

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                entry["functions"].append({
                    "name": node.name, "line": node.lineno,
                    "end_line": node.end_lineno, "is_async": isinstance(node, ast.AsyncFunctionDef),
                })
                for default in [*node.args.defaults, *node.args.kw_defaults]:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        observe(default, "mutable_default", "Mutable argument default is shared across calls.")
            elif isinstance(node, ast.ExceptHandler):
                if node.type is None or (isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}):
                    observe(node, "broad_exception", "Check whether the handler masks actionable failures.")
            elif isinstance(node, ast.Call):
                name = call_name(node.func)
                if name in {"eval", "exec", "builtins.eval", "builtins.exec"}:
                    observe(node, "dynamic_execution", f"{name}: check whether untrusted input reaches this call.")
                elif name in {"pickle.load", "pickle.loads", "yaml.load", "os.system"}:
                    observe(node, "unsafe_sink", f"{name}: inspect data provenance and safe alternatives.")
                elif name.startswith("subprocess.") and any(
                    k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True
                    for k in node.keywords
                ):
                    observe(node, "shell_execution", "shell=True; inspect interpolation and input provenance.")
                elif name.endswith((".execute", ".executemany")) and node.args and isinstance(
                    node.args[0], (ast.JoinedStr, ast.BinOp)
                ):
                    observe(node, "interpolated_sql", "Query is composed dynamically; verify parameter binding.")
    return output


def test_inventory(files: list[SourceFile]) -> dict:
    tests = [f for f in files if f.is_test]
    inventory = []
    for file in tests:
        names = re.findall(r"(?:async\s+)?def\s+(test_\w+)|\b(?:it|test)\s*\(\s*['\"]([^'\"]+)", file.content)
        inventory.append({"file": file.path, "tests": [a or b for a, b in names]})
    return {
        "test_files": inventory,
        "source_files": [f.path for f in files if not f.is_test],
        "coverage_measured": False,
        "scope": (
            "Only submitted files are visible. No tests were run; no coverage percentage is available. "
            "Missing submitted tests do not prove the repository lacks tests."
        ),
    }


def build_tools(request: ReviewRequest) -> dict[str, StructuredTool]:
    by_path = {f.path: f for f in request.files}

    def inspect_sources() -> str:
        """Read all submitted files with original 1-based line numbers. Required before reviewing."""
        return json.dumps({
            "files": [{"path": f.path, "is_test": f.is_test, "source": numbered(f)} for f in request.files],
            "python_ast": python_analysis(request.files),
            "test_inventory": test_inventory(request.files),
        })

    def read_lines(path: str, start_line: int, end_line: int) -> str:
        """Read up to 100 lines from an exact submitted path to verify a finding."""
        file = by_path.get(path)
        if file is None:
            return json.dumps({"error": "Path is not in this review snapshot."})
        if start_line < 1 or end_line < start_line or end_line - start_line >= 100:
            return json.dumps({"error": "Use a valid 1-based range of at most 100 lines."})
        return json.dumps({"path": path, "source": numbered(file, start_line, end_line)})

    def search_sources(query: str) -> str:
        """Search a literal string in submitted files; returns at most 40 matching source lines."""
        if not query or len(query) > 120:
            return json.dumps({"error": "Use a literal query of 1 to 120 characters."})
        matches = []
        for file in request.files:
            for i, line in enumerate(file.content.splitlines(), 1):
                if query.casefold() in line.casefold():
                    matches.append({"file": file.path, "line": i, "text": line[:500]})
                    if len(matches) == 40:
                        return json.dumps({"matches": matches, "truncated": True})
        return json.dumps({"matches": matches, "truncated": False})

    return {
        f.__name__: StructuredTool.from_function(f)
        for f in (inspect_sources, read_lines, search_sources)
    }


def load_source_paths(paths: list[Path]) -> list[SourceFile]:
    """Read explicitly selected code files; never follow symlinks or execute them."""
    files = []
    if not paths or len(paths) > 20:
        raise ValueError("Select between 1 and 20 code files.")
    common = Path(__import__("os").path.commonpath([str(p.absolute().parent) for p in paths]))
    for path in paths:
        if path.is_symlink() or any(p.is_symlink() for p in path.absolute().parents):
            raise ValueError("Symbolic links are not supported.")
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError("Select source code files in supported languages.")
        if path.stat().st_size > 80_000:
            raise ValueError("Each source file must be at most 80 KB.")
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeError:
            raise ValueError("Source files must use UTF-8 text.") from None
        files.append(SourceFile(path=str(path.absolute().relative_to(common)), content=content))
    return files
