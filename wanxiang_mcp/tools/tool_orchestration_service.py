"""工具编排服务 - Tool Orchestration Service

处理多工具调用的编排逻辑，防止无限循环，处理工具依赖和互斥关系。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class OrchestrationState(Enum):
    """编排状态"""
    IDLE = "idle"
    COLLECTING = "collecting"  # 收集工具调用
    EXECUTING = "executing"  # 执行中
    COMPLETED = "completed"  # 完成
    MAX_ROUNDS_REACHED = "max_rounds_reached"  # 达到最大轮次


@dataclass
class ToolCall:
    """工具调用记录"""
    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None
    executed: bool = False


@dataclass
class OrchestrationResult:
    """编排执行结果"""
    state: OrchestrationState
    tool_calls: List[ToolCall]
    final_text: str
    total_rounds: int


class ToolOrchestrationService:
    """多工具协同编排服务

    处理多工具调用的循环机制：
    - 最多允许 3 轮工具调用
    - 防止无限循环
    - 合并工具结果到上下文中
    """

    MAX_TOOL_CALL_ROUNDS = 3
    TOOL_CALL_TIMEOUT = 60.0  # 秒

    # 工具依赖关系定义
    # key: 工具名 -> 需要在该工具之前调用的工具列表
    TOOL_PREREQUISITES: Dict[str, List[str]] = {
        "chat.analyze_rumor": ["chat.search_overview"],  # 谣言分析前需先搜索
        "chat.extract_timeline": ["chat.search_overview"],  # 时间线提取前需先搜索
        "chat.verify_source_credibility": ["chat.search_overview"],  # 来源验证前需先搜索
    }

    # 互斥工具组（同一轮次只调用一个）
    MUTUALLY_EXCLUSIVE_GROUPS: List[Set[str]] = [
        {"chat.search_overview", "chat.search_web", "chat.search_web_tavily"},  # 搜索工具互斥
    ]

    @classmethod
    def get_mutually_exclusive_tool(
        cls,
        tool_names: List[str],
        existing_calls: List[ToolCall],
    ) -> Optional[str]:
        """从互斥组中选择最佳工具

        Args:
            tool_names: 请求调用的工具列表
            existing_calls: 已执行过的工具调用

        Returns:
            最佳工具名，如果列表为空则返回 None
        """
        called_tools = {tc.tool_name for tc in existing_calls if tc.executed}

        for group in cls.MUTUALLY_EXCLUSIVE_GROUPS:
            # 找出请求中属于该互斥组的工具
            candidates = [t for t in tool_names if t in group]
            if not candidates:
                continue

            # 优先选择未调用过的
            uncalled = [t for t in candidates if t not in called_tools]
            if uncalled:
                # 选择列表第一个（通常是最优的）
                return uncalled[0]

            # 都调用过了，选择最新的
            return candidates[0]

        return tool_names[0] if tool_names else None

    @classmethod
    def resolve_prerequisites(
        cls,
        tool_name: str,
        existing_calls: List[ToolCall],
    ) -> List[str]:
        """解析工具的前置依赖

        Args:
            tool_name: 目标工具名
            existing_calls: 已执行过的工具调用

        Returns:
            需要额外执行的前置工具列表
        """
        prerequisites = cls.TOOL_PREREQUISITES.get(tool_name, [])
        called_tools = {tc.tool_name for tc in existing_calls if tc.executed}

        # 返回尚未调用的依赖
        return [p for p in prerequisites if p not in called_tools]

    @classmethod
    def build_execution_order(
        cls,
        requested_tools: List[str],
        existing_calls: List[ToolCall],
    ) -> List[str]:
        """构建工具执行顺序

        考虑依赖关系和互斥组。

        Args:
            requested_tools: LLM 请求调用的工具列表
            existing_calls: 已执行过的工具调用

        Returns:
            按执行顺序排列的工具列表
        """
        execution_order: List[str] = []
        called = {tc.tool_name for tc in existing_calls if tc.executed}

        for tool in requested_tools:
            if tool in called:
                continue

            # 检查互斥组
            exclusive_tool = cls.get_mutually_exclusive_tool(
                [tool],
                existing_calls + [
                    ToolCall(tool_name=t, arguments={}, executed=True)
                    for t in execution_order
                ],
            )
            if not exclusive_tool:
                continue

            # 解析并添加前置依赖
            prereqs = cls.resolve_prerequisites(
                exclusive_tool,
                existing_calls + [
                    ToolCall(tool_name=t, arguments={}, executed=True)
                    for t in execution_order
                ],
            )
            for prereq in prereqs:
                if prereq not in called and prereq not in execution_order:
                    execution_order.append(prereq)
                    called.add(prereq)

            # 添加主工具
            if exclusive_tool not in execution_order:
                execution_order.append(exclusive_tool)
                called.add(exclusive_tool)

        return execution_order

    @classmethod
    def should_continue_loop(
        cls,
        current_round: int,
        last_tool_calls: List[ToolCall],
    ) -> bool:
        """判断是否应该继续工具调用循环

        Args:
            current_round: 当前轮次
            last_tool_calls: 上一轮的工具调用

        Returns:
            True if should continue, False otherwise
        """
        if current_round >= cls.MAX_TOOL_CALL_ROUNDS:
            return False

        # 检查是否有实际执行成功的工具调用
        has_successful_call = any(
            tc.executed and not tc.error for tc in last_tool_calls
        )

        return has_successful_call

    @classmethod
    def create_tool_call(
        cls,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> ToolCall:
        """创建一个工具调用记录"""
        return ToolCall(tool_name=tool_name, arguments=arguments)

    @classmethod
    def mark_executed(
        cls,
        tool_call: ToolCall,
        result: Any = None,
        error: Optional[str] = None,
    ) -> ToolCall:
        """标记工具调用已执行"""
        tool_call.executed = True
        tool_call.result = result
        tool_call.error = error
        return tool_call

    @classmethod
    def get_next_prerequisite(
        cls,
        tool_name: str,
        existing_calls: List[ToolCall],
    ) -> Optional[str]:
        """获取工具的下一个未执行的前置依赖

        Returns:
            下一个需要执行的前置工具名，如果没有则返回 None
        """
        prereqs = cls.resolve_prerequisites(tool_name, existing_calls)
        return prereqs[0] if prereqs else None

    @classmethod
    def is_mutually_exclusive(
        cls,
        tool1: str,
        tool2: str,
    ) -> bool:
        """判断两个工具是否互斥"""
        for group in cls.MUTUALLY_EXCLUSIVE_GROUPS:
            if tool1 in group and tool2 in group:
                return True
        return False

    @classmethod
    def get_tool_priority(cls, tool_name: str) -> int:
        """获取工具的优先级（数字越小优先级越高）"""
        priority_map = {
            "chat.search_overview": 1,  # 聚合搜索最高优先级
            "chat.analyze_rumor": 2,
            "chat.extract_timeline": 3,
            "chat.verify_source_credibility": 4,
            "chat.get_hotspot_context": 5,
            "chat.search_web": 6,
            "chat.load_urls": 7,
        }
        return priority_map.get(tool_name, 100)
