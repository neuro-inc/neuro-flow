import pytest
from funcparserlib.lexer import LexerError
from funcparserlib.parser import NoParseError
from textwrap import dedent

from neuro_flow.expr import (
    FUNCTIONS,
    PARSER,
    AttrGetter,
    Call,
    ItemGetter,
    Literal,
    Lookup,
    Text,
    tokenize,
)


def test_tmpl_ok1() -> None:
    assert [Lookup((0, 4), (0, 8), "name", [])] == PARSER.parse(
        list(tokenize("${{ name }}"))
    )


def test_tmpl_ok2() -> None:
    assert [
        Lookup(
            (0, 4),
            (0, 18),
            "name",
            [AttrGetter((0, 9), (0, 12), "sub"), AttrGetter((0, 13), (0, 18), "param")],
        )
    ] == PARSER.parse(list(tokenize("${{ name.sub.param }}")))


def test_tmpl_ok3() -> None:
    assert [Lookup((0, 3), (0, 7), "name", [])] == PARSER.parse(
        list(tokenize("${{name}}"))
    )


def test_tmpl_false1() -> None:
    with pytest.raises(LexerError):
        PARSER.parse(list(tokenize("}}")))


def test_tmpl_false2() -> None:
    with pytest.raises(NoParseError):
        PARSER.parse(list(tokenize("${{")))


def test_tmpl_false3() -> None:
    with pytest.raises(NoParseError):
        PARSER.parse(list(tokenize("${{ name sub  param")))


def test_tmpl_false4() -> None:
    with pytest.raises(NoParseError):
        PARSER.parse(list(tokenize("${{ name")))


def test_tmpl_false5() -> None:
    with pytest.raises(LexerError):
        PARSER.parse(list(tokenize("name }}")))


def test_tmpl_literal_none() -> None:
    assert [Literal((0, 4), (0, 8), None)] == PARSER.parse(
        list(tokenize("${{ None }}"))
    )


def test_tmpl_literal_real() -> None:
    assert [Literal((0, 4), (0, 9), 12.34)] == PARSER.parse(
        list(tokenize("${{ 12.34 }}"))
    )


def test_tmpl_literal_exp() -> None:
    assert [Literal((0, 4), (0, 14), -12.34e-21)] == PARSER.parse(
        list(tokenize("${{ -12.34e-21 }}"))
    )


def test_tmpl_literal_int1() -> None:
    assert [Literal((0, 4), (0, 8), 1234)] == PARSER.parse(
        list(tokenize("${{ 1234 }}"))
    )


def test_tmpl_literal_int2() -> None:
    assert [Literal((0, 4), (0, 9), 1234)] == PARSER.parse(
        list(tokenize("${{ 12_34 }}"))
    )


def test_tmpl_literal_int3() -> None:
    assert [Literal((0, 4), (0, 9), -1234)] == PARSER.parse(
        list(tokenize("${{ -1234 }}"))
    )


def test_tmpl_literal_hex1() -> None:
    assert [Literal((0, 4), (0, 10), 0x12AB)] == PARSER.parse(
        list(tokenize("${{ 0x12ab }}"))
    )


def test_tmpl_literal_hex2() -> None:
    assert [Literal((0, 4), (0, 11), 0x12AB)] == PARSER.parse(
        list(tokenize("${{ 0X12_ab }}"))
    )


def test_tmpl_literal_oct1() -> None:
    assert [Literal((0, 4), (0, 10), 0o1234)] == PARSER.parse(
        list(tokenize("${{ 0o1234 }}"))
    )


def test_tmpl_literal_oct2() -> None:
    assert [Literal((0, 4), (0, 11), 0o1234)] == PARSER.parse(
        list(tokenize("${{ 0O12_34 }}"))
    )


def test_tmpl_literal_bin1() -> None:
    assert [Literal((0, 4), (0, 10), 0b0110)] == PARSER.parse(
        list(tokenize("${{ 0b0110 }}"))
    )


def test_tmpl_literal_bin2() -> None:
    assert [Literal((0, 4), (0, 11), 0b0110)] == PARSER.parse(
        list(tokenize("${{ 0B01_10 }}"))
    )


def test_tmpl_literal_bool1() -> None:
    assert [Literal((0, 4), (0, 8), True)] == PARSER.parse(
        list(tokenize("${{ True }}"))
    )


def test_tmpl_literal_bool2() -> None:
    assert [Literal((0, 4), (0, 9), False)] == PARSER.parse(
        list(tokenize("${{ False }}"))
    )


def test_tmpl_literal_str1() -> None:
    assert [Literal((0, 4), (0, 9), "str")] == PARSER.parse(
        list(tokenize("${{ 'str' }}"))
    )


def test_tmpl_literal_str2() -> None:
    assert [Literal((0, 4), (0, 13), "abc\tdef")] == PARSER.parse(
        list(tokenize("${{ 'abc\tdef' }}"))
    )


def test_text_ok() -> None:
    assert [Text((0, 0), (0, 9), "some text")] == PARSER.parse(
        list(tokenize("some text"))
    )


def test_text_with_dot() -> None:
    assert [Text((0, 0), (0, 11), "some . text")] == PARSER.parse(
        list(tokenize("some . text"))
    )


def test_parser1() -> None:
    assert [
        Text((0, 0), (0, 5), "some "),
        Lookup((0, 9), (0, 16), "var", [AttrGetter((0, 13), (0, 16), "arg")]),
        Text((0, 19), (0, 24), " text"),
    ] == PARSER.parse(list(tokenize("some ${{ var.arg }} text")))


def test_func_call_empty() -> None:
    assert [Call((0, 4), (0, 11), FUNCTIONS["nothing"], [], [])] == PARSER.parse(
        list(tokenize("${{ nothing() }}"))
    )


def test_func_call_single_arg() -> None:
    assert [
        Call((0, 4), (0, 13), FUNCTIONS["len"], [Literal((0, 8), (0, 13), "abc")], [])
    ] == PARSER.parse(list(tokenize("${{ len('abc') }}")))


def test_func_nested_calls() -> None:
    assert [
        Call(
            (0, 4),
            (0, 16),
            FUNCTIONS["len"],
            [
                Call(
                    (0, 8),
                    (0, 16),
                    FUNCTIONS["keys"],
                    [Lookup((0, 13), (0, 16), "abc", [])],
                    [],
                )
            ],
            [],
        )
    ] == PARSER.parse(list(tokenize("${{ len(keys(abc)) }}")))


def test_func_call_multiple_args() -> None:
    assert [
        Call(
            (0, 4),
            (0, 27),
            FUNCTIONS["fmt"],
            [
                Literal((0, 8), (0, 15), "{} {}"),
                Literal((0, 17), (0, 22), "abc"),
                Literal((0, 24), (0, 27), 123),
            ],
            [],
        )
    ] == PARSER.parse(list(tokenize('${{ fmt("{} {}", "abc", 123) }}')))


def test_func_call_arg_lookup() -> None:
    assert [
        Call(
            (0, 4),
            (0, 30),
            FUNCTIONS["len"],
            [
                Lookup(
                    (0, 8),
                    (0, 30),
                    "images",
                    [
                        AttrGetter((0, 15), (0, 19), "name"),
                        AttrGetter((0, 20), (0, 30), "build_args"),
                    ],
                )
            ],
            [],
        )
    ] == PARSER.parse(list(tokenize("${{ len(images.name.build_args) }}")))


def test_func_call_with_trailer_attr() -> None:
    assert [
        Call(
            (0, 4),
            (0, 39),
            FUNCTIONS["from_json"],
            [Literal((0, 14), (0, 36), '{"a": 1, "b": "val"}')],
            [AttrGetter((0, 38), (0, 39), "a")],
        )
    ] == PARSER.parse(list(tokenize("""${{ from_json('{"a": 1, "b": "val"}').a }}""")))


def test_func_call_with_trailer_item() -> None:
    assert [
        Call(
            (0, 4),
            (0, 41),
            FUNCTIONS["from_json"],
            [Literal((0, 14), (0, 36), '{"a": 1, "b": "val"}')],
            [ItemGetter((0, 38), (0, 41), Literal((0, 38), (0, 41), "a"))],
        )
    ] == PARSER.parse(
        list(tokenize("""${{ from_json('{"a": 1, "b": "val"}')['a'] }}"""))
    )


def test_corner_case1() -> None:
    s = dedent(
        """\
            jupyter notebook
              --no-browser
              --ip=0.0.0.0
              --allow-root
              --NotebookApp.token=
              --notebook-dir=${{ volumes.notebooks.mount }}
        """
    )
    assert (
        [
            Text(
                (0, 0),
                (5, 17),
                dedent(
                    """\
                        jupyter notebook
                          --no-browser
                          --ip=0.0.0.0
                          --allow-root
                          --NotebookApp.token=
                          --notebook-dir="""
                ),
            ),
            Lookup(
                (5, 21),
                (5, 44),
                "volumes",
                [
                    AttrGetter((5, 29), (5, 38), "notebooks"),
                    AttrGetter((5, 39), (5, 44), "mount"),
                ],
            ),
            Text((5, 47), (6, 0), "\n"),
        ]
        == PARSER.parse(list(tokenize(s)))
    )


def test_corner_case2() -> None:
    s = dedent(
        """\
            bash -c 'cd ${{ volumes.project.mount }} &&
              python -u ${{ volumes.code.mount }}/train.py
                --data ${{ volumes.data.mount }}'
        """
    )
    assert [
        Text((0, 0), (0, 12), "bash -c 'cd "),
        Lookup(
            (0, 16),
            (0, 37),
            "volumes",
            [
                AttrGetter((0, 24), (0, 31), "project"),
                AttrGetter((0, 32), (0, 37), "mount"),
            ],
        ),
        Text((0, 40), (1, 12), " &&\n  python -u "),
        Lookup(
            (1, 16),
            (1, 34),
            "volumes",
            [
                AttrGetter((1, 24), (1, 28), "code"),
                AttrGetter((1, 29), (1, 34), "mount"),
            ],
        ),
        Text((1, 37), (2, 11), "/train.py\n    --data "),
        Lookup(
            (2, 15),
            (2, 33),
            "volumes",
            [
                AttrGetter((2, 23), (2, 27), "data"),
                AttrGetter((2, 28), (2, 33), "mount"),
            ],
        ),
        Text((2, 36), (3, 0), "'\n"),
    ] == PARSER.parse(list(tokenize(s)))
