import tempfile
import unittest
import gzip
from pathlib import Path

from personal_agent.tools.app_tool import AppOpenTool
from personal_agent.tools.file_tool import FileTool
from personal_agent.tools.http_tool import HttpRequestTool
from personal_agent.tools.os_config_tool import OSConfigTool
from personal_agent.tools.shell_tool import ShellTool, is_safe_readonly_command
from personal_agent.tools.web_tool import WebTool


class ToolTests(unittest.TestCase):
    def test_file_tool_reads_existing_text_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.txt"
            path.write_text("你好，Babyface", encoding="utf-8")

            result = FileTool().run({"path": str(path)})

        self.assertTrue(result.ok)
        self.assertEqual(result.content, "你好，Babyface")

    def test_file_tool_reports_missing_file(self) -> None:
        result = FileTool().run({"path": "/no/such/file.txt"})

        self.assertFalse(result.ok)
        self.assertIn("文件不存在", result.error or "")

    def test_shell_tool_returns_stdout_stderr_and_exit_code_after_confirmation(self) -> None:
        tool = ShellTool(timeout_seconds=3, confirm=lambda command: True)

        result = tool.run({"command": "printf hello"})

        self.assertTrue(result.ok)
        self.assertEqual(result.content, "hello")
        self.assertEqual(result.metadata["exit_code"], 0)
        self.assertEqual(result.metadata["stderr"], "")

    def test_shell_tool_does_not_execute_when_user_rejects(self) -> None:
        tool = ShellTool(timeout_seconds=3, confirm=lambda command: False)

        result = tool.run({"command": "touch should-not-run"})

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "用户取消执行")
        self.assertEqual(result.metadata["exit_code"], None)

    def test_shell_tool_runs_safe_readonly_command_without_confirmation(self) -> None:
        confirmed_commands: list[str] = []
        tool = ShellTool(timeout_seconds=3, confirm=lambda command: confirmed_commands.append(command) or False)

        result = tool.run({"command": "pwd"})

        self.assertTrue(result.ok)
        self.assertEqual(confirmed_commands, [])
        self.assertEqual(result.metadata["confirmation_required"], False)

    def test_shell_readonly_classifier_rejects_destructive_git_branch_flag(self) -> None:
        self.assertFalse(is_safe_readonly_command("git branch -D old-feature"))

    def test_os_config_tool_returns_basic_config_without_directory_shell_or_environment(self) -> None:
        result = OSConfigTool().run({})

        self.assertTrue(result.ok)
        self.assertIn("操作系统", result.content)
        self.assertIn("系统版本", result.content)
        self.assertIn("CPU 架构", result.content)
        self.assertIn("用户目录", result.content)
        self.assertIn("主机名", result.content)
        self.assertIn("语言区域", result.content)
        self.assertIn("是否 macOS", result.content)
        self.assertNotIn("当前工作目录", result.content)
        self.assertNotIn("默认 Shell", result.content)
        self.assertNotIn("环境变量", result.content)

    def test_app_open_tool_opens_direct_match_on_macos(self) -> None:
        opened: list[str] = []
        tool = AppOpenTool(
            platform_name_provider=lambda: "Darwin",
            app_dirs_provider=lambda: [],
            opener=lambda app_name: opened.append(app_name) or (0, "", ""),
        )

        result = tool.run({"app_name": "Calculator"})

        self.assertTrue(result.ok)
        self.assertEqual(opened, ["Calculator"])
        self.assertEqual(result.metadata["match_method"], "direct")

    def test_app_open_tool_uses_closest_installed_app_when_direct_open_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            apps_dir = Path(tmp)
            (apps_dir / "Visual Studio Code.app").mkdir()
            (apps_dir / "Calendar.app").mkdir()
            opened: list[str] = []
            tool = AppOpenTool(
                platform_name_provider=lambda: "Darwin",
                app_dirs_provider=lambda: [apps_dir],
                opener=lambda app_name: (1, "", "not found")
                if app_name == "code editor"
                else opened.append(app_name) or (0, "", ""),
            )

            result = tool.run({"app_name": "code editor"})

        self.assertTrue(result.ok)
        self.assertEqual(opened, ["Visual Studio Code"])
        self.assertEqual(result.metadata["match_method"], "fuzzy")
        self.assertEqual(result.metadata["matched_app"], "Visual Studio Code")

    def test_app_open_tool_matches_localized_app_display_name_before_direct_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            apps_dir = Path(tmp)
            broken_app = apps_dir / "BrokenEncoding.app" / "Contents" / "Resources" / "zh-Hans.lproj"
            broken_app.mkdir(parents=True)
            (broken_app / "InfoPlist.strings").write_bytes(b"\xdf\xff\x00broken")
            app_path = apps_dir / "NeteaseMusic.app"
            zh_dir = app_path / "Contents" / "Resources" / "zh-Hans.lproj"
            zh_dir.mkdir(parents=True)
            (zh_dir / "InfoPlist.strings").write_text(
                '"CFBundleDisplayName" = "网易云音乐";\n'
                '"CFBundleName" = "网易云音乐";\n',
                encoding="utf-8",
            )
            opened: list[str] = []
            tool = AppOpenTool(
                platform_name_provider=lambda: "Darwin",
                app_dirs_provider=lambda: [apps_dir],
                opener=lambda app_name: opened.append(app_name) or (0, "", ""),
            )

            result = tool.run({"app_name": "打开网易云音乐APP"})

        self.assertTrue(result.ok)
        self.assertEqual(opened, ["NeteaseMusic"])
        self.assertEqual(result.metadata["match_method"], "fuzzy")
        self.assertEqual(result.metadata["matched_app"], "NeteaseMusic")
        self.assertIn("网易云音乐", result.metadata["matched_aliases"])

    def test_app_open_tool_rejects_when_no_close_candidate_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            apps_dir = Path(tmp)
            (apps_dir / "Calendar.app").mkdir()
            tool = AppOpenTool(
                platform_name_provider=lambda: "Darwin",
                app_dirs_provider=lambda: [apps_dir],
                opener=lambda app_name: (1, "", "not found"),
                match_threshold=0.9,
            )

            result = tool.run({"app_name": "music maker"})

        self.assertFalse(result.ok)
        self.assertIn("没有找到足够接近的应用", result.error or "")

    def test_app_open_tool_rejects_non_macos(self) -> None:
        tool = AppOpenTool(platform_name_provider=lambda: "Linux")

        result = tool.run({"app_name": "Calculator"})

        self.assertFalse(result.ok)
        self.assertIn("仅支持 macOS", result.error or "")

    def test_app_open_tool_requires_app_name(self) -> None:
        result = AppOpenTool().run({})

        self.assertFalse(result.ok)
        self.assertIn("缺少 App 名称", result.error or "")

    def test_http_request_tool_parses_json_response(self) -> None:
        tool = HttpRequestTool(opener=lambda request, *, timeout: FakeHttpResponse(
            body=b'{"message":"hello"}',
            headers={"Content-Type": "application/json"},
            status=201,
        ))

        result = tool.run({"url": "https://example.test/api"})

        self.assertTrue(result.ok)
        self.assertIn('"message": "hello"', result.content)
        self.assertEqual(result.metadata["status_code"], 201)
        self.assertEqual(result.metadata["response_type"], "json")

    def test_http_request_tool_passes_timeout_as_keyword_argument(self) -> None:
        """防止真实 `urlopen` 把 timeout 误当成 request body 参数。"""

        calls: list[float] = []

        def opener(request, *, timeout):
            calls.append(timeout)
            return FakeHttpResponse(body=b"ok", headers={"Content-Type": "text/plain"})

        result = HttpRequestTool(opener=opener).run({"url": "https://example.test", "timeout_seconds": 2})

        self.assertTrue(result.ok)
        self.assertEqual(calls, [2.0])

    def test_http_request_tool_uses_browser_headers_by_default(self) -> None:
        """防止网页站点因为 `urllib` 裸请求画像而返回 412 等反爬状态。"""

        captured_headers: list[dict[str, str]] = []

        def opener(request, *, timeout):
            captured_headers.append(dict(request.header_items()))
            return FakeHttpResponse(body=b"ok", headers={"Content-Type": "text/plain"})

        result = HttpRequestTool(opener=opener).run({"url": "https://example.test/video"})

        self.assertTrue(result.ok)
        self.assertIn("Mozilla/5.0", captured_headers[0]["User-agent"])
        self.assertIn("text/html", captured_headers[0]["Accept"])
        self.assertIn("zh-CN", captured_headers[0]["Accept-language"])
        self.assertEqual(captured_headers[0]["Accept-encoding"], "gzip")

    def test_http_request_tool_allows_user_headers_to_override_defaults(self) -> None:
        """用户显式传入 headers 时应覆盖默认请求头，方便访问特殊 API。"""

        captured_headers: list[dict[str, str]] = []

        def opener(request, *, timeout):
            captured_headers.append(dict(request.header_items()))
            return FakeHttpResponse(body=b"ok", headers={"Content-Type": "text/plain"})

        result = HttpRequestTool(opener=opener).run({
            "url": "https://example.test/api",
            "headers": {
                "User-Agent": "CustomClient/1.0",
                "Accept": "application/json",
            },
        })

        self.assertTrue(result.ok)
        self.assertEqual(captured_headers[0]["User-agent"], "CustomClient/1.0")
        self.assertEqual(captured_headers[0]["Accept"], "application/json")
        self.assertIn("Accept-language", captured_headers[0])

    def test_http_request_tool_returns_text_response(self) -> None:
        tool = HttpRequestTool(max_body_chars=5, opener=lambda request, *, timeout: FakeHttpResponse(
            body=b"hello world",
            headers={"Content-Type": "text/plain"},
        ))

        result = tool.run({"url": "https://example.test/text"})

        self.assertTrue(result.ok)
        self.assertIn("hello", result.content)
        self.assertEqual(result.metadata["response_type"], "text")
        self.assertTrue(result.metadata["truncated"])

    def test_http_request_tool_decompresses_gzip_html_and_extracts_title(self) -> None:
        """防止 gzip 页面被当成乱码，导致模型根据空信息编造网页标题。"""

        html = "<html><head><title>真实视频标题</title></head><body>正文</body></html>"
        tool = HttpRequestTool(opener=lambda request, *, timeout: FakeHttpResponse(
            body=gzip.compress(html.encode("utf-8")),
            headers={"Content-Type": "text/html; charset=utf-8", "Content-Encoding": "gzip"},
        ))

        result = tool.run({"url": "https://example.test/video"})

        self.assertTrue(result.ok)
        self.assertIn("网页标题: 真实视频标题", result.content)
        self.assertIn("正文", result.content)
        self.assertEqual(result.metadata["response_type"], "html")
        self.assertEqual(result.metadata["title"], "真实视频标题")
        self.assertFalse(result.metadata["compressed"])

    def test_http_request_tool_rejects_unsupported_protocol(self) -> None:
        result = HttpRequestTool().run({"url": "file:///tmp/a.txt"})

        self.assertFalse(result.ok)
        self.assertIn("仅支持 HTTP 和 HTTPS", result.error or "")

    def test_http_request_tool_reports_network_error(self) -> None:
        def fail(_request, *, timeout):
            raise OSError("network down")

        result = HttpRequestTool(opener=fail).run({"url": "https://example.test"})

        self.assertFalse(result.ok)
        self.assertIn("HTTP 请求失败", result.error or "")

    def test_http_request_tool_parses_sse_events(self) -> None:
        tool = HttpRequestTool(opener=lambda request, *, timeout: FakeHttpResponse(
            body=b"id: 1\nevent: message\ndata: hello\n\ndata: world\n\n",
            headers={"Content-Type": "text/event-stream"},
        ))

        result = tool.run({"url": "https://example.test/events", "max_sse_events": 2})

        self.assertTrue(result.ok)
        self.assertIn("hello", result.content)
        self.assertIn("world", result.content)
        self.assertEqual(result.metadata["response_type"], "sse")
        self.assertEqual(result.metadata["event_count"], 2)
        self.assertEqual(result.metadata["stop_reason"], "event_limit")

    def test_http_request_tool_returns_partial_sse_events_on_connection_end(self) -> None:
        tool = HttpRequestTool(opener=lambda request, *, timeout: FakeHttpResponse(
            body=b"data: only-one\n\n",
            headers={"Content-Type": "text/event-stream"},
        ))

        result = tool.run({"url": "https://example.test/events", "max_sse_events": 5})

        self.assertTrue(result.ok)
        self.assertIn("only-one", result.content)
        self.assertEqual(result.metadata["stop_reason"], "connection_closed")

    def test_web_tool_returns_not_implemented_result(self) -> None:
        result = WebTool().run({"query": "今天新闻"})

        self.assertFalse(result.ok)
        self.assertIn("尚未实现", result.error or "")


class FakeHttpResponse:
    """测试用的 HTTP 响应替身。

    真实 `urllib` 响应对象同时提供 `read()`、`readline()`、`headers` 和 `status`。
    这里只实现 HTTP Tool 会用到的最小行为，避免单元测试访问真实网络。
    """

    def __init__(self, body: bytes, headers: dict[str, str], status: int = 200) -> None:
        self._body = body
        self._lines = iter(body.splitlines(keepends=True))
        self.headers = headers
        self.status = status

    def read(self) -> bytes:
        """返回完整响应体，模拟普通 HTTP 响应读取。"""

        return self._body

    def readline(self) -> bytes:
        """逐行返回响应体，模拟 SSE 流式读取。"""

        return next(self._lines, b"")

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


if __name__ == "__main__":
    unittest.main()
