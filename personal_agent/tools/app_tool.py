from __future__ import annotations

import difflib
import platform
import re
import subprocess
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from personal_agent.tools.base import ToolResult


OpenResult = tuple[int, str, str]


class AppOpenTool:
    """打开 macOS App 的本地工具。

    工具先尝试按用户输入直接打开 App；如果系统找不到该 App，
    再扫描常见应用目录并按相似度选择最接近的候选。这样用户说
    “代码编辑器”或输入不完整名称时，Agent 仍有机会打开正确应用。
    """

    name = "app_open"
    description = "在 macOS 上按名称或描述打开本机 App。"

    def __init__(
        self,
        *,
        platform_name_provider: Callable[[], str] = platform.system,
        app_dirs_provider: Callable[[], Iterable[Path]] | None = None,
        opener: Callable[[str], OpenResult] | None = None,
        match_threshold: float = 0.42,
    ) -> None:
        self.platform_name_provider = platform_name_provider
        self.app_dirs_provider = app_dirs_provider or self._default_app_dirs
        self.opener = opener or self._open_app
        self.match_threshold = match_threshold

    def to_openai_tool(self) -> dict[str, Any]:
        """声明打开 App 工具的输入 schema。"""

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "app_name": {"type": "string", "description": "App 名称或用户描述"}
                    },
                    "required": ["app_name"],
                },
            },
        }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        """按名称或描述打开 macOS App。"""

        app_name = str(arguments.get("app_name") or "").strip()
        if not app_name:
            return ToolResult(ok=False, error="缺少 App 名称。")

        if self.platform_name_provider() != "Darwin":
            return ToolResult(
                ok=False,
                error="打开 App Tool 当前仅支持 macOS。",
                metadata={"app_name": app_name, "platform": self.platform_name_provider()},
            )

        exit_code, stdout, stderr = self.opener(app_name)
        if exit_code == 0:
            return ToolResult(
                ok=True,
                content=f"已请求系统打开 App：{app_name}",
                metadata={
                    "app_name": app_name,
                    "matched_app": app_name,
                    "match_method": "direct",
                    "exit_code": exit_code,
                    "stdout": stdout,
                    "stderr": stderr,
                },
            )

        match = self._find_best_app_match(app_name)
        if match is None:
            return ToolResult(
                ok=False,
                error="没有找到足够接近的应用。",
                metadata={
                    "app_name": app_name,
                    "match_method": "none",
                    "exit_code": exit_code,
                    "stdout": stdout,
                    "stderr": stderr,
                },
            )

        matched_name, matched_path, score = match
        retry_code, retry_stdout, retry_stderr = self.opener(matched_name)
        if retry_code != 0:
            return ToolResult(
                ok=False,
                error="打开 App 失败。",
                metadata={
                    "app_name": app_name,
                    "matched_app": matched_name,
                    "matched_path": str(matched_path),
                    "match_score": score,
                    "match_method": "fuzzy",
                    "exit_code": retry_code,
                    "stdout": retry_stdout,
                    "stderr": retry_stderr,
                },
            )

        return ToolResult(
            ok=True,
            content=f"已根据描述“{app_name}”请求系统打开最接近的 App：{matched_name}",
            metadata={
                "app_name": app_name,
                "matched_app": matched_name,
                "matched_path": str(matched_path),
                "match_score": score,
                "match_method": "fuzzy",
                "exit_code": retry_code,
                "stdout": retry_stdout,
                "stderr": retry_stderr,
            },
        )

    def _find_best_app_match(self, query: str) -> tuple[str, Path, float] | None:
        """扫描已安装 App，并返回达到阈值的最佳候选。"""

        candidates = list(self._iter_installed_apps())
        scored = [
            (name, path, self._match_score(query, name))
            for name, path in candidates
        ]
        if not scored:
            return None
        best_name, best_path, best_score = max(scored, key=lambda item: item[2])
        if best_score < self.match_threshold:
            return None
        return best_name, best_path, best_score

    def _iter_installed_apps(self) -> Iterable[tuple[str, Path]]:
        """枚举常见 macOS 应用目录下的 `.app` 包。"""

        seen: set[str] = set()
        for app_dir in self.app_dirs_provider():
            if not app_dir.exists() or not app_dir.is_dir():
                continue
            for path in app_dir.glob("*.app"):
                name = path.stem.strip()
                key = name.casefold()
                if name and key not in seen:
                    seen.add(key)
                    yield name, path

    def _match_score(self, query: str, app_name: str) -> float:
        """计算用户描述与 App 名称的相似度。

        分数同时考虑整体字符串相似度和词元重叠。比如 `code editor`
        与 `Visual Studio Code` 至少共享 `code`，可以被识别为近似候选。
        """

        normalized_query = self._normalize(query)
        normalized_app = self._normalize(app_name)
        string_score = difflib.SequenceMatcher(None, normalized_query, normalized_app).ratio()
        query_tokens = set(normalized_query.split())
        app_tokens = set(normalized_app.split())
        overlap_score = len(query_tokens & app_tokens) / len(query_tokens) if query_tokens else 0.0
        return max(string_score, overlap_score)

    def _normalize(self, text: str) -> str:
        """把名称归一化为适合相似度比较的形式。"""

        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.casefold())).strip()

    def _default_app_dirs(self) -> list[Path]:
        """返回 macOS 常见应用目录。"""

        return [
            Path("/Applications"),
            Path("/System/Applications"),
            Path.home() / "Applications",
        ]

    def _open_app(self, app_name: str) -> OpenResult:
        """调用 macOS `open -a` 打开 App，并返回进程结果。"""

        completed = subprocess.run(
            ["open", "-a", app_name],
            check=False,
            capture_output=True,
            text=True,
        )
        return completed.returncode, completed.stdout, completed.stderr
