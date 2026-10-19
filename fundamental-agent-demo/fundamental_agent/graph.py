"""演示用的小型 DAG 运行器。

这些节点边界与项目走出零依赖 MVP 后将使用的 LangGraph StateGraph
结构保持一致。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable


NodeRun = Callable[[dict[str, Any]], dict[str, Any] | None]


@dataclass(frozen=True)
class Node:
    name: str
    run: NodeRun
    depends_on: tuple[str, ...] = field(default_factory=tuple)


class DagGraph:
    """具有显式依赖关系的确定性 DAG 运行器。"""

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}

    def add_node(self, node: Node) -> None:
        if node.name in self._nodes:
            raise ValueError(f"duplicate node: {node.name}")
        missing = [dep for dep in node.depends_on if dep not in self._nodes]
        if missing:
            raise ValueError(f"node {node.name} depends on unknown nodes: {missing}")
        self._nodes[node.name] = node

    def run(self, state: dict[str, Any] | None = None) -> dict[str, Any]:
        state = dict(state or {})
        # _topological_order() 会返回一个满足依赖关系的节点名列表
        for name in self._topological_order():
            result = self._nodes[name].run(state)
            if result:
                state.update(result)
        return state

    def _topological_order(self) -> list[str]:
        indegree = {name: 0 for name in self._nodes}
        children: dict[str, list[str]] = {name: [] for name in self._nodes}

        for name, node in self._nodes.items():
            for dep in node.depends_on:
                indegree[name] += 1
                children[dep].append(name)

        queue = deque(name for name, degree in indegree.items() if degree == 0)
        order: list[str] = []

        while queue:
            name = queue.popleft()
            order.append(name)
            for child in children[name]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)

        if len(order) != len(self._nodes):
            raise ValueError("graph contains a cycle")
        return order
