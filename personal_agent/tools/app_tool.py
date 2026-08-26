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
                        "app_name": {
                            "type": "string",
                            "description": "用户想打开的 App 名称或自然语言描述，工具会扫描 macOS 应用目录并做名称匹配",
                        }
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

        match = self._find_best_app_match(app_name)
        if match is not None:
            matched_name, matched_path, score, aliases = match
            exit_code, stdout, stderr = self.opener(matched_name)
            if exit_code == 0:
                return ToolResult(
                    ok=True,
                    content=f"已成功打开 App：{matched_name}",
                    metadata={
                        "app_name": app_name,
                        "matched_app": matched_name,
                        "matched_path": str(matched_path),
                        "matched_aliases": aliases,
                        "match_score": score,
                        "match_method": "fuzzy",
                        "exit_code": exit_code,
                        "stdout": stdout,
                        "stderr": stderr,
                    },
                )

            return ToolResult(
                ok=False,
                error="打开 App 失败。",
                metadata={
                    "app_name": app_name,
                    "matched_app": matched_name,
                    "matched_path": str(matched_path),
                    "matched_aliases": aliases,
                    "match_score": score,
                    "match_method": "fuzzy",
                    "exit_code": exit_code,
                    "stdout": stdout,
                    "stderr": stderr,
                },
            )

        exit_code, stdout, stderr = self.opener(app_name)
        if exit_code == 0:
            return ToolResult(
                ok=True,
                content=f"已成功打开 App：{app_name}",
                metadata={
                    "app_name": app_name,
                    "matched_app": app_name,
                    "match_method": "direct",
                    "exit_code": exit_code,
                    "stdout": stdout,
                    "stderr": stderr,
                },
            )

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

    def _find_best_app_match(self, query: str) -> tuple[str, Path, float, list[str]] | None:
        """扫描已安装 App，并返回达到阈值的最佳候选。"""

        candidates = list(self._iter_installed_apps())
        scored = [
            (name, path, self._best_alias_score(query, aliases), aliases)
            for name, path, aliases in candidates
        ]
        if not scored:
            return None
        best_name, best_path, best_score, best_aliases = max(scored, key=lambda item: item[2])
        if best_score < self.match_threshold:
            return None
        return best_name, best_path, best_score, best_aliases

    def _iter_installed_apps(self) -> Iterable[tuple[str, Path, list[str]]]:
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
                    yield name, path, self._app_aliases(path, name)

    def _app_aliases(self, app_path: Path, app_name: str) -> list[str]:
        """读取 App 的英文目录名和本地化显示名作为匹配别名。

        macOS App 的 `.app` 目录名常常是英文，例如 `NeteaseMusic.app`；
        用户自然语言里更可能说“网易云音乐”。读取 `InfoPlist.strings`
        能把这两个名字连接起来。
        """

        aliases = [app_name]
        resources_dir = app_path / "Contents" / "Resources"
        for strings_path in resources_dir.glob("*.lproj/InfoPlist.strings"):
            content = self._read_plist_strings(strings_path)
            if content is None:
                continue
            for key in ("CFBundleDisplayName", "CFBundleName"):
                match = re.search(rf'"{key}"\s*=\s*"(?P<value>[^"]+)"\s*;', content)
                if match:
                    aliases.append(match.group("value").strip())

        unique_aliases: list[str] = []
        seen_aliases: set[str] = set()
        for alias in aliases:
            key = alias.casefold()
            if alias and key not in seen_aliases:
                seen_aliases.add(key)
                unique_aliases.append(alias)
        return unique_aliases

    def _read_plist_strings(self, path: Path) -> str | None:
        """读取 `InfoPlist.strings`，无法解码时返回 None。

        不同 App 的本地化字符串文件编码并不完全一致。这里按常见编码逐个
        尝试，仍失败就跳过该文件，避免一个异常 App 阻断整个目录扫描。
        """

        try:
            raw_content = path.read_bytes()
        except OSError:
            return None
        for encoding in ("utf-8", "utf-16", "utf-16-le", "utf-16-be"):
            try:
                return raw_content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return None

    def _best_alias_score(self, query: str, aliases: list[str]) -> float:
        """计算用户描述与多个 App 别名中的最高匹配分。"""

        return max((self._match_score(query, alias) for alias in aliases), default=0.0)

    def _match_score(self, query: str, app_name: str) -> float:
        """计算用户描述与 App 名称的相似度。

        分数同时考虑整体字符串相似度和词元重叠。比如 `code editor`
        与 `Visual Studio Code` 至少共享 `code`，可以被识别为近似候选。
        """

        clean_query = self._normalize(query)
        clean_app = self._normalize(app_name)
        if not clean_query or not clean_app:
            return 0.0
        if clean_app in clean_query or clean_query in clean_app:
            return 1.0
        string_score = difflib.SequenceMatcher(None, clean_query, clean_app).ratio()
        query_tokens = set(clean_query.split())
        app_tokens = set(clean_app.split())
        overlap_score = len(query_tokens & app_tokens) / len(query_tokens) if query_tokens else 0.0
        return max(string_score, overlap_score)

    def _normalize(self, text: str) -> str:
        """把名称归一化为适合相似度比较的形式。

        这里保留中文字符，避免“网易云音乐”这类输入被清洗成空字符串。
        """

        without_app_suffix = re.sub(r"(?i)\bapp\b", " ", text)
        return re.sub(
            r"\s+",
            " ",
            re.sub(r"[^\w\u4e00-\u9fff]+", " ", without_app_suffix.casefold()),
        ).strip()

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
