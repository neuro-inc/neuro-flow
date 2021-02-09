from collections import defaultdict
from typing import AbstractSet, Dict, Generic, Mapping, Set, TypeVar


_K = TypeVar("_K")
_T = TypeVar("_T")


class CycleError(ValueError):
    pass


class ColoredTopoSorter(Generic[_K, _T]):
    def __init__(self, graph: Mapping[_K, Mapping[_K, _T]]):
        self._graph = graph
        self._node_rev_deps: Dict[_K, Dict[_T, Set[_K]]] = defaultdict(
            lambda: defaultdict(set)
        )
        self._node_deps_cnt: Dict[_K, int] = dict()
        self._color2nodes: Dict[_T, Set[_K]] = defaultdict(set)
        self._ready = set()
        for node, deps in graph.items():
            if not deps:
                self._ready.add(node)
            self._node_deps_cnt[node] = len(deps)
            for dep_node, dep_color in deps.items():
                self._node_rev_deps[dep_node][dep_color].add(node)
        self._check_cycle()

    def _check_cycle(self) -> None:
        seen = set()
        stack = []
        for start_node in self._graph:
            if start_node in seen:
                continue
            stack.append(start_node)
            seen_step = set()
            while stack:
                node = stack.pop()
                if node in seen:
                    continue
                if node in seen_step:
                    raise CycleError()
                seen_step.add(node)
                stack.extend(self._graph[node])
            seen.update(seen_step)

    def mark(self, node: _K, color: _T) -> None:
        if node in self._color2nodes[color]:
            return  # Already marked with this color
        self._color2nodes[color].add(node)
        for rev_node in self._node_rev_deps[node][color]:
            self._node_deps_cnt[rev_node] -= 1
            if self._node_deps_cnt[rev_node] == 0:
                self._ready.add(rev_node)

    def is_all_colored(self, color: _T) -> bool:
        return len(self._color2nodes[color]) == len(self._graph)

    def get_ready(self) -> AbstractSet[_K]:
        ret = self._ready
        self._ready = set()
        return ret
