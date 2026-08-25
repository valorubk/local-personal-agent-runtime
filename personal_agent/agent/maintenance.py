from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from personal_agent.agent.llm import LLMClient
from personal_agent.prompt_profile import AGENTS_FILENAME, build_agents_prompt, replace_managed_preferences
from personal_agent.text import sanitize_text_for_runtime


AGENTS_UPDATE_JUDGE_PROMPT = """你负责判断本轮 Babyface 任务是否产生了值得写入 AGENTS.md 的长期用户偏好。
请只提取稳定、长期、可复用的偏好或工作方式，不记录一次性任务内容，不记录敏感信息。
如果不确定，返回 should_update=false。
每轮最多返回一条候选规则。
用户明确使用“记住”“以后”“每次”“一定要”等表达长期回复方式或工作偏好时，应倾向于返回 should_update=true。
默认 target 使用 global；只有用户明确要求写入当前项目或当前目录时，target 才能使用 project 或 current。
必须只返回 JSON，不要返回 Markdown。JSON 格式：
{"should_update": false}
或：
{"should_update": true, "target": "global|project|current", "preference": "一条中文规则", "reason": "为什么这是长期偏好"}"""


AGENTS_UPDATE_FORCED_EXTRACTION_PROMPT = f"""{AGENTS_UPDATE_JUDGE_PROMPT}

这次用户输入中出现了明确的长期偏好表达。请重新判断并尽量抽取候选规则。
除非该输入明显不是长期偏好，否则不要返回 should_update=false。"""


AGENTS_CONFLICT_RESOLUTION_PROMPT = """你负责在写入单个 AGENTS.md 前整理 Babyface managed section。
输入会包含目标 AGENTS.md 当前全文和一条候选规则。
请判断候选规则是否与现有规则重复或冲突。
如果冲突，请返回解决冲突后的 managed_preferences 列表，用新规则替换被冲突覆盖的旧规则。
不要改写 managed section 之外的任何用户手写内容。
必须只返回 JSON，不要返回 Markdown。JSON 格式：
{"managed_preferences": ["规则一", "规则二"], "conflict_resolution": "简短说明"}"""


AgentsUpdateTarget = Literal["global", "project", "current"]


@dataclass(frozen=True)
class PostTurnMaintenanceContext:
    """一轮任务结束后交给维护服务的上下文。

    Runtime 只提供已经清洗过的本轮事实和 `AGENTS.md` 路径边界，不需要知道
    LLM 候选判断、冲突整理或 managed section 写入细节。未来如果维护服务升级为
    独立 Steward Agent，也可以继续沿用这个输入边界。
    """

    user_input: str
    final_response: str
    agents_home: Path | None = None
    current_dir: Path | None = None
    workspace_root: Path | None = None


@dataclass(frozen=True)
class AgentsUpdateCandidate:
    """LLM 对本轮任务是否需要更新 `AGENTS.md` 的结构化判断。

    `target` 表示候选规则应写入的层级；`preference` 是候选规则正文；
    `reason` 记录为什么该规则适合沉淀为长期 prompt 偏好。
    """

    target: AgentsUpdateTarget
    preference: str
    reason: str


@dataclass(frozen=True)
class AgentsMdMaintenanceResult:
    """一次 `AGENTS.md` 维护流程的可审计结果。

    V1 不把该结果展示给用户；它主要用于测试和后续审计扩展。真正写入仍由
    `replace_managed_preferences()` 限制在 managed section 内。
    """

    target_path: Path
    candidate: AgentsUpdateCandidate
    resolved_preferences: list[str]
    conflict_resolution: str


AgentsUpdateProposal = AgentsMdMaintenanceResult


class AgentsMdMaintenanceService:
    """负责 post-turn `AGENTS.md` 自动维护的服务。

    该服务位于主 Agent Loop 之外：它接收一轮任务上下文，先用确定性规则确认
    用户是否明示要求长期记住偏好；只有明示时才调用 LLM 判断候选规则，随后
    读取单个目标 `AGENTS.md`，让 LLM 整理 managed section，最后执行受控写入。
    Runtime 只负责编排调用，不直接理解这些维护细节。
    """

    def __init__(self, llm: LLMClient) -> None:
        """创建维护服务。

        参数：
        - `llm`：用于候选判断和冲突整理的 LLM 客户端。测试会注入 fake client，
          避免访问真实网络。
        """

        self.llm = llm

    def run(self, context: PostTurnMaintenanceContext) -> AgentsMdMaintenanceResult | None:
        """同步执行一轮 post-turn `AGENTS.md` 维护。

        返回 `None` 表示本轮没有可写入的长期规则；返回结果对象表示已经按
        managed section 安全边界完成写入。当前 V1 不引入异步 worker，因此调用方
        可以获得确定的写入顺序和简单的 CLI 退出语义。
        """

        if not _looks_like_explicit_agents_preference(context.user_input):
            return None

        candidate = self._judge_agents_update_candidate(context)
        if candidate is None:
            candidate = self._judge_agents_update_candidate(context, force_explicit=True)
            if candidate is None:
                return None

        target_path = self._resolve_agents_update_path(candidate.target, context)
        result = self._resolve_agents_update_conflicts(target_path, candidate)
        replace_managed_preferences(target_path, result.resolved_preferences)
        return result

    def _judge_agents_update_candidate(
        self,
        context: PostTurnMaintenanceContext,
        force_explicit: bool = False,
    ) -> AgentsUpdateCandidate | None:
        """调用 LLM 判断本轮是否产生了可写入 `AGENTS.md` 的长期偏好。"""

        messages = [
            {
                "role": "system",
                "content": AGENTS_UPDATE_FORCED_EXTRACTION_PROMPT if force_explicit else AGENTS_UPDATE_JUDGE_PROMPT,
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_input": context.user_input,
                        "final_response": context.final_response,
                        "当前已加载的 AGENTS.md": build_agents_prompt(
                            home=context.agents_home,
                            current_dir=context.current_dir,
                            workspace_root=context.workspace_root,
                        ),
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        response = self.llm.complete(messages, [])
        data = _load_json_object(response.content)
        if not data.get("should_update"):
            return None

        target = str(data.get("target") or "global")
        if target not in {"global", "project", "current"}:
            target = "global"
        preference = sanitize_text_for_runtime(str(data.get("preference") or "")).strip()
        if not preference:
            return None
        reason = sanitize_text_for_runtime(str(data.get("reason") or "LLM 判断这是长期偏好。")).strip()
        return AgentsUpdateCandidate(
            target=target,  # type: ignore[arg-type]
            preference=preference,
            reason=reason,
        )

    def _resolve_agents_update_conflicts(
        self,
        target_path: Path,
        candidate: AgentsUpdateCandidate,
    ) -> AgentsMdMaintenanceResult:
        """调用 LLM 整理目标文件 managed section，生成写入结果。"""

        current_content = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
        messages = [
            {"role": "system", "content": AGENTS_CONFLICT_RESOLUTION_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "target_path": str(target_path),
                        "current_agents_md": current_content,
                        "candidate_preference": candidate.preference,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        response = self.llm.complete(messages, [])
        data = _load_json_object(response.content)
        raw_preferences = data.get("managed_preferences")
        if isinstance(raw_preferences, list):
            resolved = [sanitize_text_for_runtime(str(item)).strip() for item in raw_preferences if str(item).strip()]
        else:
            resolved = [candidate.preference]
        conflict_resolution = sanitize_text_for_runtime(str(data.get("conflict_resolution") or "")).strip()
        return AgentsMdMaintenanceResult(
            target_path=target_path,
            candidate=candidate,
            resolved_preferences=resolved,
            conflict_resolution=conflict_resolution,
        )

    def _resolve_agents_update_path(
        self,
        target: AgentsUpdateTarget,
        context: PostTurnMaintenanceContext,
    ) -> Path:
        """根据 LLM 给出的目标层级，解析实际要写入的 `AGENTS.md` 路径。"""

        home = context.agents_home or Path(os.environ.get("HOME", str(Path.home())))
        if target == "project":
            root = context.workspace_root or context.current_dir or Path.cwd()
            return root / AGENTS_FILENAME
        if target == "current":
            current = context.current_dir or Path.cwd()
            return current / AGENTS_FILENAME
        return home / ".babyface" / AGENTS_FILENAME


def _load_json_object(content: str) -> dict[str, Any]:
    """把 LLM 输出解析成 JSON 对象，解析失败时返回空对象。

    `AGENTS.md` 维护是主任务之后的附加流程。模型偶尔返回非 JSON 时，维护服务
    应该安全跳过，而不是破坏本轮用户任务已经生成的最终回答。
    """

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict):
        return data
    return {}


def _looks_like_explicit_agents_preference(user_input: str) -> bool:
    """判断用户是否显式表达了希望长期改变 Babyface 行为。

    这个启发式只用于触发第二次 LLM 抽取，不直接决定写入内容。真正写入的规则
    仍必须来自 LLM 返回的结构化候选。
    """

    text = user_input.strip()
    if not text:
        return False
    has_memory_verb = any(keyword in text for keyword in ("记住", "以后", "后续", "每次", "一定要", "固定"))
    has_behavior_target = any(keyword in text for keyword in ("回复", "回答", "跟我", "对话", "工作", "风格", "偏好"))
    return has_memory_verb and has_behavior_target
