import operator
import pytest
from funcparserlib.parser import NoParseError
from textwrap import dedent
from typing import Any
from typing_extensions import Final

from neuro_flow.expr import (
    FUNCTIONS,
    PARSER,
    AttrGetter,
    BinOp,
    Call,
    DictMaker,
    ItemGetter,
    ListMaker,
    Literal,
    Lookup,
    Text,
    UnaryOp,
    logical_and,
    logical_or,
)
from neuro_flow.tokenizer import LexerError, Pos, tokenize
from neuro_flow.types import LocalPath


FNAME = LocalPath("<test>")
START: Final = Pos(0, 0, FNAME)


def test_tmpl_ok1() -> None:
    assert [Lookup(Pos(0, 4, FNAME), Pos(0, 8, FNAME), "name", [])] == PARSER.parse(
        list(tokenize("${{ name }}", START))
    )


def test_tmpl_ok2() -> None:
    assert [
        Lookup(
            Pos(0, 4, FNAME),
            Pos(0, 18, FNAME),
            "name",
            [
                AttrGetter(Pos(0, 9, FNAME), Pos(0, 12, FNAME), "sub"),
                AttrGetter(Pos(0, 13, FNAME), Pos(0, 18, FNAME), "param"),
            ],
        )
    ] == PARSER.parse(list(tokenize("${{ name.sub.param }}", START)))


def test_tmpl_ok3() -> None:
    assert [Lookup(Pos(0, 3, FNAME), Pos(0, 7, FNAME), "name", [])] == PARSER.parse(
        list(tokenize("${{name}}", START))
    )


def test_tmpl_ok4() -> None:
    assert [Lookup(Pos(0, 4, FNAME), Pos(0, 8, FNAME), "name", [])] == PARSER.parse(
        list(tokenize("$[[ name ]]", START))
    )


def test_tmpl_ok5() -> None:
    assert [
        Lookup(
            Pos(0, 4, FNAME),
            Pos(0, 18, FNAME),
            "name",
            [
                AttrGetter(Pos(0, 9, FNAME), Pos(0, 12, FNAME), "sub"),
                AttrGetter(Pos(0, 13, FNAME), Pos(0, 18, FNAME), "param"),
            ],
        )
    ] == PARSER.parse(list(tokenize("$[[ name.sub.param ]]", START)))


def test_tmpl_ok6() -> None:
    assert [Lookup(Pos(0, 3, FNAME), Pos(0, 7, FNAME), "name", [])] == PARSER.parse(
        list(tokenize("$[[name]]", START))
    )


def test_tmpl_false1() -> None:
    with pytest.raises(LexerError):
        PARSER.parse(list(tokenize("}}", START)))


def test_tmpl_false2() -> None:
    with pytest.raises(NoParseError):
        PARSER.parse(list(tokenize("${{", START)))


def test_tmpl_false3() -> None:
    with pytest.raises(NoParseError):
        PARSER.parse(list(tokenize("${{ name sub  param", START)))


def test_tmpl_false4() -> None:
    with pytest.raises(NoParseError):
        PARSER.parse(list(tokenize("${{ name", START)))


def test_tmpl_false5() -> None:
    with pytest.raises(LexerError):
        PARSER.parse(list(tokenize("name }}", START)))


def test_tmpl_false6() -> None:
    with pytest.raises(LexerError):
        PARSER.parse(list(tokenize("]]", START)))


def test_tmpl_false7() -> None:
    with pytest.raises(NoParseError):
        PARSER.parse(list(tokenize("$[[", START)))


def test_tmpl_false8() -> None:
    with pytest.raises(NoParseError):
        PARSER.parse(list(tokenize("$[[ name sub  param", START)))


def test_tmpl_false9() -> None:
    with pytest.raises(NoParseError):
        PARSER.parse(list(tokenize("$[[ name", START)))


def test_tmpl_false10() -> None:
    with pytest.raises(LexerError):
        PARSER.parse(list(tokenize("name ]]", START)))


def test_tmpl_literal_none() -> None:
    assert [Literal(Pos(0, 4, FNAME), Pos(0, 8, FNAME), None)] == PARSER.parse(
        list(tokenize("${{ None }}", START))
    )


def test_tmpl_literal_real() -> None:
    assert [Literal(Pos(0, 4, FNAME), Pos(0, 9, FNAME), 12.34)] == PARSER.parse(
        list(tokenize("${{ 12.34 }}", START))
    )


def test_tmpl_literal_exp() -> None:
    assert [Literal(Pos(0, 4, FNAME), Pos(0, 14, FNAME), -12.34e-21)] == PARSER.parse(
        list(tokenize("${{ -12.34e-21 }}", START))
    )


def test_tmpl_literal_int1() -> None:
    assert [Literal(Pos(0, 4, FNAME), Pos(0, 8, FNAME), 1234)] == PARSER.parse(
        list(tokenize("${{ 1234 }}", START))
    )


def test_tmpl_literal_int2() -> None:
    assert [Literal(Pos(0, 4, FNAME), Pos(0, 9, FNAME), 1234)] == PARSER.parse(
        list(tokenize("${{ 12_34 }}", START))
    )


def test_tmpl_literal_int3() -> None:
    assert [Literal(Pos(0, 4, FNAME), Pos(0, 9, FNAME), -1234)] == PARSER.parse(
        list(tokenize("${{ -1234 }}", START))
    )


def test_tmpl_literal_hex1() -> None:
    assert [Literal(Pos(0, 4, FNAME), Pos(0, 10, FNAME), 0x12AB)] == PARSER.parse(
        list(tokenize("${{ 0x12ab }}", START))
    )


def test_tmpl_literal_hex2() -> None:
    assert [Literal(Pos(0, 4, FNAME), Pos(0, 11, FNAME), 0x12AB)] == PARSER.parse(
        list(tokenize("${{ 0X12_ab }}", START))
    )


def test_tmpl_literal_oct1() -> None:
    assert [Literal(Pos(0, 4, FNAME), Pos(0, 10, FNAME), 0o1234)] == PARSER.parse(
        list(tokenize("${{ 0o1234 }}", START))
    )


def test_tmpl_literal_oct2() -> None:
    assert [Literal(Pos(0, 4, FNAME), Pos(0, 11, FNAME), 0o1234)] == PARSER.parse(
        list(tokenize("${{ 0O12_34 }}", START))
    )


def test_tmpl_literal_bin1() -> None:
    assert [Literal(Pos(0, 4, FNAME), Pos(0, 10, FNAME), 0b0110)] == PARSER.parse(
        list(tokenize("${{ 0b0110 }}", START))
    )


def test_tmpl_literal_bin2() -> None:
    assert [Literal(Pos(0, 4, FNAME), Pos(0, 11, FNAME), 0b0110)] == PARSER.parse(
        list(tokenize("${{ 0B01_10 }}", START))
    )


def test_tmpl_literal_bool1() -> None:
    assert [Literal(Pos(0, 4, FNAME), Pos(0, 8, FNAME), True)] == PARSER.parse(
        list(tokenize("${{ True }}", START))
    )


def test_tmpl_literal_bool2() -> None:
    assert [Literal(Pos(0, 4, FNAME), Pos(0, 9, FNAME), False)] == PARSER.parse(
        list(tokenize("${{ False }}", START))
    )


def test_tmpl_literal_str1() -> None:
    assert [Literal(Pos(0, 4, FNAME), Pos(0, 9, FNAME), "str")] == PARSER.parse(
        list(tokenize("${{ 'str' }}", START))
    )


def test_tmpl_literal_str2() -> None:
    assert [Literal(Pos(0, 4, FNAME), Pos(0, 13, FNAME), "abc\tdef")] == PARSER.parse(
        list(tokenize("${{ 'abc\tdef' }}", START))
    )


def test_text_ok() -> None:
    assert [Text(Pos(0, 0, FNAME), Pos(0, 9, FNAME), "some text")] == PARSER.parse(
        list(tokenize("some text", START))
    )


def test_text_with_dot() -> None:
    assert [Text(Pos(0, 0, FNAME), Pos(0, 11, FNAME), "some . text")] == PARSER.parse(
        list(tokenize("some . text", START))
    )


def test_parser1() -> None:
    assert [
        Text(Pos(0, 0, FNAME), Pos(0, 5, FNAME), "some "),
        Lookup(
            Pos(0, 9, FNAME),
            Pos(0, 16, FNAME),
            "var",
            [AttrGetter(Pos(0, 13, FNAME), Pos(0, 16, FNAME), "arg")],
        ),
        Text(Pos(0, 19, FNAME), Pos(0, 24, FNAME), " text"),
    ] == PARSER.parse(list(tokenize("some ${{ var.arg }} text", START)))


def test_func_call_empty() -> None:
    assert [
        Call(Pos(0, 4, FNAME), Pos(0, 11, FNAME), FUNCTIONS["nothing"], [], [])
    ] == PARSER.parse(list(tokenize("${{ nothing() }}", START)))


def test_func_call_single_arg() -> None:
    assert [
        Call(
            Pos(0, 4, FNAME),
            Pos(0, 13, FNAME),
            FUNCTIONS["len"],
            [Literal(Pos(0, 8, FNAME), Pos(0, 13, FNAME), "abc")],
            [],
        )
    ] == PARSER.parse(list(tokenize("${{ len('abc') }}", START)))


def test_func_nested_calls() -> None:
    assert [
        Call(
            Pos(0, 4, FNAME),
            Pos(0, 16, FNAME),
            FUNCTIONS["len"],
            [
                Call(
                    Pos(0, 8, FNAME),
                    Pos(0, 16, FNAME),
                    FUNCTIONS["keys"],
                    [Lookup(Pos(0, 13, FNAME), Pos(0, 16, FNAME), "abc", [])],
                    [],
                )
            ],
            [],
        )
    ] == PARSER.parse(list(tokenize("${{ len(keys(abc)) }}", START)))


def test_func_call_multiple_args() -> None:
    assert [
        Call(
            Pos(0, 4, FNAME),
            Pos(0, 27, FNAME),
            FUNCTIONS["fmt"],
            [
                Literal(Pos(0, 8, FNAME), Pos(0, 15, FNAME), "{} {}"),
                Literal(Pos(0, 17, FNAME), Pos(0, 22, FNAME), "abc"),
                Literal(Pos(0, 24, FNAME), Pos(0, 27, FNAME), 123),
            ],
            [],
        )
    ] == PARSER.parse(list(tokenize('${{ fmt("{} {}", "abc", 123) }}', START)))


def test_func_call_arg_lookup() -> None:
    assert [
        Call(
            Pos(0, 4, FNAME),
            Pos(0, 30, FNAME),
            FUNCTIONS["len"],
            [
                Lookup(
                    Pos(0, 8, FNAME),
                    Pos(0, 30, FNAME),
                    "images",
                    [
                        AttrGetter(Pos(0, 15, FNAME), Pos(0, 19, FNAME), "name"),
                        AttrGetter(Pos(0, 20, FNAME), Pos(0, 30, FNAME), "build_args"),
                    ],
                )
            ],
            [],
        )
    ] == PARSER.parse(list(tokenize("${{ len(images.name.build_args) }}", START)))


def test_func_call_with_trailer_attr() -> None:
    assert [
        Call(
            Pos(0, 4, FNAME),
            Pos(0, 39, FNAME),
            FUNCTIONS["from_json"],
            [Literal(Pos(0, 14, FNAME), Pos(0, 36, FNAME), '{"a": 1, "b": "val"}')],
            [AttrGetter(Pos(0, 38, FNAME), Pos(0, 39, FNAME), "a")],
        )
    ] == PARSER.parse(
        list(tokenize("""${{ from_json('{"a": 1, "b": "val"}').a }}""", START))
    )


def test_func_call_with_trailer_item() -> None:
    assert [
        Call(
            Pos(0, 4, FNAME),
            Pos(0, 41, FNAME),
            FUNCTIONS["from_json"],
            [Literal(Pos(0, 14, FNAME), Pos(0, 36, FNAME), '{"a": 1, "b": "val"}')],
            [
                ItemGetter(
                    Pos(0, 38, FNAME),
                    Pos(0, 41, FNAME),
                    Literal(Pos(0, 38, FNAME), Pos(0, 41, FNAME), "a"),
                )
            ],
        )
    ] == PARSER.parse(
        list(tokenize("""${{ from_json('{"a": 1, "b": "val"}')['a'] }}""", START))
    )


@pytest.mark.parametrize(
    "op_str,op_func",
    [
        ("==", operator.eq),
        ("!=", operator.ne),
        ("or", logical_or),
        ("and", logical_and),
        ("<", operator.lt),
        ("<=", operator.le),
        (">", operator.gt),
        (">=", operator.ge),
    ],
)
def test_operator_parse(op_str: str, op_func: Any) -> None:
    assert [
        BinOp(
            Pos(0, 4, FNAME),
            Pos(0, 14 + len(op_str), FNAME),
            op_func,
            Lookup(Pos(0, 4, FNAME), Pos(0, 7, FNAME), "foo", []),
            Literal(
                Pos(0, 9 + len(op_str), FNAME),
                Pos(0, 14 + len(op_str), FNAME),
                "bar",
            ),
        )
    ] == PARSER.parse(list(tokenize(f"""${{{{ foo {op_str} "bar" }}}}""", START)))


@pytest.mark.parametrize(
    "op_str,op_func",
    [
        ("not", operator.not_),
    ],
)
def test_unary_operator_parse(op_str: str, op_func: Any) -> None:
    assert [
        UnaryOp(
            Pos(0, 4, FNAME),
            Pos(0, 10 + len(op_str), FNAME),
            op_func,
            Literal(
                Pos(0, 5 + len(op_str), FNAME),
                Pos(0, 10 + len(op_str), FNAME),
                "bar",
            ),
        )
    ] == PARSER.parse(list(tokenize(f"""${{{{ {op_str} "bar" }}}}""", START)))


def test_operator_parse_brackets() -> None:
    assert [
        BinOp(
            start=Pos(line=0, col=4, filename=FNAME),
            end=Pos(line=0, col=24, filename=FNAME),
            op=logical_or,
            left=Lookup(
                start=Pos(line=0, col=4, filename=FNAME),
                end=Pos(line=0, col=7, filename=FNAME),
                root="foo",
                trailer=[],
            ),
            right=BinOp(
                start=Pos(line=0, col=12, filename=FNAME),
                end=Pos(line=0, col=24, filename=FNAME),
                op=operator.eq,
                left=Lookup(
                    start=Pos(line=0, col=12, filename=FNAME),
                    end=Pos(line=0, col=15, filename=FNAME),
                    root="bar",
                    trailer=[],
                ),
                right=Literal(
                    start=Pos(line=0, col=19, filename=FNAME),
                    end=Pos(line=0, col=24, filename=FNAME),
                    val="baz",
                ),
            ),
        )
    ] == PARSER.parse(list(tokenize("""${{ foo or (bar == "baz") }}""", START)))


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
                Pos(0, 0, FNAME),
                Pos(5, 17, FNAME),
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
                Pos(5, 21, FNAME),
                Pos(5, 44, FNAME),
                "volumes",
                [
                    AttrGetter(Pos(5, 29, FNAME), Pos(5, 38, FNAME), "notebooks"),
                    AttrGetter(Pos(5, 39, FNAME), Pos(5, 44, FNAME), "mount"),
                ],
            ),
            Text(Pos(5, 47, FNAME), Pos(6, 0, FNAME), "\n"),
        ]
        == PARSER.parse(list(tokenize(s, START)))
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
        Text(Pos(0, 0, FNAME), Pos(0, 12, FNAME), "bash -c 'cd "),
        Lookup(
            Pos(0, 16, FNAME),
            Pos(0, 37, FNAME),
            "volumes",
            [
                AttrGetter(Pos(0, 24, FNAME), Pos(0, 31, FNAME), "project"),
                AttrGetter(Pos(0, 32, FNAME), Pos(0, 37, FNAME), "mount"),
            ],
        ),
        Text(Pos(0, 40, FNAME), Pos(1, 12, FNAME), " &&\n  python -u "),
        Lookup(
            Pos(1, 16, FNAME),
            Pos(1, 34, FNAME),
            "volumes",
            [
                AttrGetter(Pos(1, 24, FNAME), Pos(1, 28, FNAME), "code"),
                AttrGetter(Pos(1, 29, FNAME), Pos(1, 34, FNAME), "mount"),
            ],
        ),
        Text(Pos(1, 37, FNAME), Pos(2, 11, FNAME), "/train.py\n    --data "),
        Lookup(
            Pos(2, 15, FNAME),
            Pos(2, 33, FNAME),
            "volumes",
            [
                AttrGetter(Pos(2, 23, FNAME), Pos(2, 27, FNAME), "data"),
                AttrGetter(Pos(2, 28, FNAME), Pos(2, 33, FNAME), "mount"),
            ],
        ),
        Text(Pos(2, 36, FNAME), Pos(3, 0, FNAME), "'\n"),
    ] == PARSER.parse(list(tokenize(s, START)))


def test_list() -> None:
    assert [
        ListMaker(
            start=Pos(0, 4, FNAME),
            end=Pos(0, 25, FNAME),
            items=[
                Literal(
                    start=Pos(0, 4, FNAME),
                    end=Pos(0, 5, FNAME),
                    val=1,
                ),
                Literal(
                    start=Pos(0, 7, FNAME),
                    end=Pos(0, 10, FNAME),
                    val="2",
                ),
                Literal(
                    start=Pos(0, 12, FNAME),
                    end=Pos(0, 16, FNAME),
                    val=True,
                ),
                Call(
                    start=Pos(0, 18, FNAME),
                    end=Pos(0, 25, FNAME),
                    func=FUNCTIONS["len"],
                    args=[
                        Lookup(
                            start=Pos(0, 22, FNAME),
                            end=Pos(0, 25, FNAME),
                            root="ctx",
                            trailer=[],
                        )
                    ],
                    trailer=[],
                ),
            ],
        )
    ] == PARSER.parse(list(tokenize("${{[1, '2', True, len(ctx)]}}", START)))


def test_dict() -> None:
    assert [
        DictMaker(
            start=Pos(0, 5, FNAME),
            end=Pos(0, 26, FNAME),
            items=[
                (
                    Literal(
                        start=Pos(0, 5, FNAME),
                        end=Pos(0, 6, FNAME),
                        val=1,
                    ),
                    Literal(
                        start=Pos(0, 8, FNAME),
                        end=Pos(0, 11, FNAME),
                        val="2",
                    ),
                ),
                (
                    Literal(
                        start=Pos(0, 13, FNAME),
                        end=Pos(0, 17, FNAME),
                        val=True,
                    ),
                    Call(
                        start=Pos(0, 19, FNAME),
                        end=Pos(0, 26, FNAME),
                        func=FUNCTIONS["len"],
                        args=[
                            Lookup(
                                start=Pos(0, 23, FNAME),
                                end=Pos(0, 26, FNAME),
                                root="ctx",
                                trailer=[],
                            )
                        ],
                        trailer=[],
                    ),
                ),
            ],
        )
    ] == PARSER.parse(list(tokenize("${{ {1: '2', True: len(ctx)} }}", START)))


def test_dict_short() -> None:
    assert [
        DictMaker(
            start=Pos(0, 5, FNAME),
            end=Pos(0, 11, FNAME),
            items=[
                (
                    Literal(
                        start=Pos(0, 5, FNAME),
                        end=Pos(0, 6, FNAME),
                        val=1,
                    ),
                    Literal(
                        start=Pos(0, 8, FNAME),
                        end=Pos(0, 11, FNAME),
                        val="2",
                    ),
                ),
            ],
        )
    ] == PARSER.parse(list(tokenize("${{ {1: '2'} }}", START)))
