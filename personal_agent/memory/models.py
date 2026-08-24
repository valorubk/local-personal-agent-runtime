from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class TaskHistory:
    """一条任务历史记录。

    这是从 SQLite 读出来后给 Python 代码使用的数据形态。
    把数据库 row 转成 dataclass 的好处是：调用方不需要知道 SQL 字段顺序。
    """

    id: int
    user_input: str
    final_response: str
    created_at: datetime
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
