import pytest
from typing import Mapping, Sequence, Set, Tuple

from neuro_flow.colored_topo_sorter import ColoredTopoSorter, CycleError


@pytest.mark.parametrize(
    "graph,colorings,expected_ready",
    [
        (  # Sequential deps with one color
            {
                1: {},
                2: {1: "a"},
                3: {2: "a"},
                4: {3: "a"},
            },
            [(1, "a"), (2, "a"), (3, "a")],
            [{1}, {2}, {3}, {4}],
        ),
        (  # Sequential deps with multi color
            {
                1: {},
                2: {1: "a"},
                3: {2: "b"},
                4: {3: "c"},
            },
            [(1, "a"), (2, "b"), (3, "c")],
            [{1}, {2}, {3}, {4}],
        ),
        (  # Diamond graph one color
            {
                1: {},
                2: {1: "a"},
                3: {1: "a"},
                4: {2: "a", 3: "a"},
            },
            [(1, "a"), (2, "a"), (3, "a")],
            [{1}, {2, 3}, set(), {4}],
        ),
        (  # Diamond graph multiple color
            {
                1: {},
                2: {1: "a"},
                3: {1: "b"},
                4: {2: "a", 3: "a"},
            },
            [(1, "a"), (1, "b"), (2, "a"), (3, "a")],
            [{1}, {2}, {3}, set(), {4}],
        ),
        (  # Diamond graph multiple color
            {
                1: {},
                2: {1: "a"},
                3: {1: "b"},
                4: {2: "a", 3: "a"},
            },
            [(1, "a"), (1, "b"), (2, "a"), (3, "a")],
            [{1}, {2}, {3}, set(), {4}],
        ),
        (  # Complex graph 1
            {
                1: {},
                2: {1: "a"},
                3: {1: "b", 2: "a"},
                4: {2: "b"},
                5: {3: "c", 4: "a"},
                6: {5: "b"},
            },
            [
                (1, "a"),
                (2, "a"),
                (1, "b"),
                (3, "a"),
                (2, "b"),
                (4, "a"),
                (3, "c"),
                (5, "b"),
            ],
            [{1}, {2}, set(), {3}, set(), {4}, set(), {5}, {6}],
        ),
        (  # Complex graph 2
            {
                1: {},
                2: {},
                3: {1: "b", 2: "a"},
                4: {1: "a", 2: "b"},
                5: {3: "b", 4: "a"},
                6: {3: "a", 4: "b"},
                7: {1: "b", 3: "b", 6: "b"},
            },
            [
                (1, "a"),
                (2, "a"),
                (1, "b"),
                (2, "b"),
                (3, "a"),
                (4, "b"),
                (3, "b"),
                (4, "a"),
                (6, "b"),
            ],
            [{1, 2}, set(), set(), {3}, {4}, set(), {6}, set(), {5}, {7}],
        ),
    ],
)
def test_graphs(
    graph: Mapping[int, Mapping[int, str]],
    colorings: Sequence[Tuple[int, str]],
    expected_ready: Sequence[Set[int]],
) -> None:
    topo = ColoredTopoSorter(graph)
    for (node, color), ready in zip(colorings, expected_ready):
        assert topo.get_ready() == ready
        topo.mark(node, color)
    assert topo.get_ready() == expected_ready[-1]


@pytest.mark.parametrize(
    "graph",
    [
        {1: {2: "a"}, 2: {1: "b"}},  # 2 cycle
        {1: {2: "a"}, 2: {3: "b"}, 3: {1: "c"}},  # 3 cycle
        {1: {2: "a"}, 2: {3: "b"}, 3: {4: "c"}, 4: {1: "d"}},  # 4 cycle
        {  # 4 cycle with additional nodes I
            1: {2: "a"},
            2: {3: "b"},
            3: {4: "c"},
            4: {1: "d"},
            5: {1: "a", 2: "b"},
        },
        {  # 4 cycle with additional nodes II
            1: {2: "a"},
            2: {3: "b"},
            3: {4: "c"},
            4: {1: "d"},
            5: {1: "a", 2: "b"},
            6: {3: "a", 2: "b"},
            7: {3: "a", 6: "b", 4: "f"},
        },
    ],
)
def test_cycle(
    graph: Mapping[int, Mapping[int, str]],
) -> None:
    with pytest.raises(CycleError):
        ColoredTopoSorter(graph)


def test_all_colored() -> None:
    graph: Mapping[int, Mapping[int, str]] = {
        1: {},
        2: {1: "a"},
        3: {2: "a"},
        4: {3: "a"},
    }
    topo = ColoredTopoSorter(graph)
    assert not topo.is_all_colored("a")
    topo.mark(1, "a")
    topo.mark(2, "a")
    topo.mark(3, "a")
    topo.mark(4, "b")
    assert not topo.is_all_colored("a")
    topo.mark(4, "a")
    assert topo.is_all_colored("a")
    assert not topo.is_all_colored("b")
    topo.mark(1, "b")
    topo.mark(2, "b")
    topo.mark(3, "b")
    assert topo.is_all_colored("b")
