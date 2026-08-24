"""Babyface 本地个人 Agent Runtime。

这个 package 是项目的 Python 主包。初学时可以按下面顺序阅读：

1. `config.py`：配置如何从环境变量/文件进入程序
2. `tools/`：LLM 如何调用本地能力
3. `memory/`：SQLite 如何保存长期信息和任务历史
4. `agent/llm.py`：如何封装 OpenAI-compatible LLM
5. `agent/runtime.py`：LangGraph 如何串起 Agent Loop
6. `main.py`：Typer/Rich 如何提供交互式 CLI
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
