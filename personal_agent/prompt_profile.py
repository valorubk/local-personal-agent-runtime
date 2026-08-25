from __future__ import annotations

import os
from pathlib import Path


AGENTS_FILENAME = "AGENTS.md"
AGENTS_MANAGED_START = "<!-- babyface-managed:start -->"
AGENTS_MANAGED_END = "<!-- babyface-managed:end -->"
LEARNED_PREFERENCES_HEADING = "## Babyface Learned Preferences"


def discover_agents_files(
    home: Path | None = None,
    current_dir: Path | None = None,
    workspace_root: Path | None = None,
) -> list[Path]:
    """按全局到局部的顺序返回存在的 `AGENTS.md` 文件。"""

    resolved_home = _resolve_home(home)
    resolved_current = (current_dir or Path.cwd()).resolve()
    resolved_workspace = _resolve_workspace_root(resolved_current, resolved_home, workspace_root)

    candidates: list[Path] = []
    if resolved_home is not None:
        candidates.append(resolved_home / ".babyface" / AGENTS_FILENAME)

    for directory in _directory_chain(resolved_workspace, resolved_current):
        candidates.append(directory / AGENTS_FILENAME)

    seen: set[Path] = set()
    files: list[Path] = []
    for candidate in candidates:
        resolved_candidate = candidate.resolve()
        if resolved_candidate in seen:
            continue
        seen.add(resolved_candidate)
        if candidate.is_file():
            files.append(candidate)
    return files


def build_agents_prompt(
    home: Path | None = None,
    current_dir: Path | None = None,
    workspace_root: Path | None = None,
) -> str:
    """读取并拼接 `AGENTS.md`，保留来源边界和文件原文。"""

    sections: list[str] = []
    for path in discover_agents_files(home=home, current_dir=current_dir, workspace_root=workspace_root):
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            continue
        sections.append(f"## AGENTS.md\nSource: {path}\n\n{content.rstrip()}")
    return "\n\n".join(sections)


def upsert_global_preference(home: Path, preference: str) -> Path:
    """把长期偏好写入全局 managed section。"""

    path = home / ".babyface" / AGENTS_FILENAME
    return upsert_agents_preference(path, preference)


def upsert_agents_preference(path: Path, preference: str) -> Path:
    """把长期偏好写入指定 `AGENTS.md` 的 managed section。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    normalized_preference = _normalize_preference(preference)
    content = _read_or_create_agents_content(path)
    preferences = _read_managed_preferences(content)
    if normalized_preference not in preferences:
        preferences.append(normalized_preference)
    return replace_managed_preferences(path, preferences)


def replace_managed_preferences(path: Path, preferences: list[str]) -> Path:
    """用给定规则列表替换目标 `AGENTS.md` 的 managed section。

    这个函数只改 `babyface-managed` 标记之间的内容。标记之外的用户手写
    Markdown 会原样保留，避免 LLM 冲突整理时顺手改掉用户明确写下的项目规则。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    content = _read_or_create_agents_content(path)
    if AGENTS_MANAGED_START not in content or AGENTS_MANAGED_END not in content:
        content = _append_managed_section(content)

    before, managed_and_after = content.split(AGENTS_MANAGED_START, 1)
    _managed, after = managed_and_after.split(AGENTS_MANAGED_END, 1)
    normalized_preferences = [_normalize_preference(preference) for preference in preferences if preference.strip()]
    managed_content = "\n".join(dict.fromkeys(normalized_preferences))
    if managed_content:
        managed_content = f"\n{managed_content}\n"
    else:
        managed_content = "\n"

    updated = f"{before}{AGENTS_MANAGED_START}{managed_content}{AGENTS_MANAGED_END}{after}"
    path.write_text(_ensure_trailing_newline(updated), encoding="utf-8")
    return path


def _read_or_create_agents_content(path: Path) -> str:
    """读取目标 `AGENTS.md`，不存在时返回默认 Markdown 骨架。"""

    if path.exists():
        return path.read_text(encoding="utf-8")
    return "# AGENTS.md\n\n"


def _read_managed_preferences(content: str) -> list[str]:
    """从 managed section 中读取现有规则，缺少标记时返回空列表。"""

    if AGENTS_MANAGED_START not in content or AGENTS_MANAGED_END not in content:
        return []
    _before, managed_and_after = content.split(AGENTS_MANAGED_START, 1)
    managed, after = managed_and_after.split(AGENTS_MANAGED_END, 1)
    return [line.strip() for line in managed.splitlines() if line.strip()]


def _resolve_home(home: Path | None) -> Path | None:
    if home is not None:
        return home.resolve()
    raw_home = os.environ.get("HOME")
    if not raw_home:
        return None
    return Path(raw_home).resolve()


def _resolve_workspace_root(
    current_dir: Path,
    home: Path | None,
    workspace_root: Path | None,
) -> Path:
    if workspace_root is not None:
        return workspace_root.resolve()

    git_root = _find_git_root(current_dir)
    if git_root is not None:
        return git_root

    if home is not None:
        try:
            current_dir.relative_to(home)
            return home
        except ValueError:
            pass
    return current_dir


def _find_git_root(current_dir: Path) -> Path | None:
    for directory in [current_dir, *current_dir.parents]:
        if (directory / ".git").exists():
            return directory
    return None


def _directory_chain(start: Path, end: Path) -> list[Path]:
    try:
        end.relative_to(start)
    except ValueError:
        return [end]

    chain = [end]
    while chain[-1] != start:
        chain.append(chain[-1].parent)
    return list(reversed(chain))


def _append_managed_section(content: str) -> str:
    base = content.rstrip()
    if base:
        base += "\n\n"
    return "\n".join(
        [
            base + LEARNED_PREFERENCES_HEADING,
            "",
            AGENTS_MANAGED_START,
            AGENTS_MANAGED_END,
            "",
        ]
    )


def _normalize_preference(preference: str) -> str:
    text = preference.strip()
    if text.startswith("- "):
        return text
    return f"- {text}"


def _ensure_trailing_newline(content: str) -> str:
    if content.endswith("\n"):
        return content
    return f"{content}\n"
