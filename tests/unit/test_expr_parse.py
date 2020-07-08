from textwrap import dedent

import pytest
from funcparserlib.lexer import LexerError
from funcparserlib.parser import NoParseError

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
    assert [Lookup("name", [])] == PARSER.parse(list(tokenize("${{ name }}")))


def test_tmpl_ok2() -> None:
    assert [Lookup("name", [AttrGetter("sub"), AttrGetter("param")])] == PARSER.parse(
        list(tokenize("${{ name.sub.param }}"))
    )


def test_tmpl_ok3() -> None:
    assert [Lookup("name", [])] == PARSER.parse(list(tokenize("${{name}}")))


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
    assert [Literal(None)] == PARSER.parse(list(tokenize("${{ None }}")))


def test_tmpl_literal_real() -> None:
    assert [Literal(12.34)] == PARSER.parse(list(tokenize("${{ 12.34 }}")))


def test_tmpl_literal_exp() -> None:
    assert [Literal(-12.34e-21)] == PARSER.parse(list(tokenize("${{ -12.34e-21 }}")))


def test_tmpl_literal_int1() -> None:
    assert [Literal(1234)] == PARSER.parse(list(tokenize("${{ 1234 }}")))


def test_tmpl_literal_int2() -> None:
    assert [Literal(1234)] == PARSER.parse(list(tokenize("${{ 12_34 }}")))


def test_tmpl_literal_int3() -> None:
    assert [Literal(-1234)] == PARSER.parse(list(tokenize("${{ -1234 }}")))


def test_tmpl_literal_hex1() -> None:
    assert [Literal(0x12AB)] == PARSER.parse(list(tokenize("${{ 0x12ab }}")))


def test_tmpl_literal_hex2() -> None:
    assert [Literal(0x12AB)] == PARSER.parse(list(tokenize("${{ 0X12_ab }}")))


def test_tmpl_literal_oct1() -> None:
    assert [Literal(0o1234)] == PARSER.parse(list(tokenize("${{ 0o1234 }}")))


def test_tmpl_literal_oct2() -> None:
    assert [Literal(0o1234)] == PARSER.parse(list(tokenize("${{ 0O12_34 }}")))


def test_tmpl_literal_bin1() -> None:
    assert [Literal(0b0110)] == PARSER.parse(list(tokenize("${{ 0b0110 }}")))


def test_tmpl_literal_bin2() -> None:
    assert [Literal(0b0110)] == PARSER.parse(list(tokenize("${{ 0B01_10 }}")))


def test_tmpl_literal_bool1() -> None:
    assert [Literal(True)] == PARSER.parse(list(tokenize("${{ True }}")))


def test_tmpl_literal_bool2() -> None:
    assert [Literal(False)] == PARSER.parse(list(tokenize("${{ False }}")))


def test_tmpl_literal_str1() -> None:
    assert [Literal("str")] == PARSER.parse(list(tokenize("${{ 'str' }}")))


def test_tmpl_literal_str2() -> None:
    assert [Literal("abc\tdef")] == PARSER.parse(list(tokenize("${{ 'abc\tdef' }}")))


def test_text_ok() -> None:
    assert [Text("some text")] == PARSER.parse(list(tokenize("some text")))


def test_text_with_dot() -> None:
    assert [Text("some . text")] == PARSER.parse(list(tokenize("some . text")))


def test_parser1() -> None:
    assert [
        Text("some "),
        Lookup("var", [AttrGetter("arg")]),
        Text(" text"),
    ] == PARSER.parse(list(tokenize("some ${{ var.arg }} text")))


def test_func_call_empty() -> None:
    assert [Call(FUNCTIONS["nothing"], [], [])] == PARSER.parse(
        list(tokenize("${{ nothing() }}"))
    )


def test_func_call_single_arg() -> None:
    assert [Call(FUNCTIONS["len"], [Literal("abc")], [])] == PARSER.parse(
        list(tokenize("${{ len('abc') }}"))
    )


def test_func_nested_calls() -> None:
    assert [
        Call(FUNCTIONS["len"], [Call(FUNCTIONS["keys"], [Lookup("abc", [])], [])], [])
    ] == PARSER.parse(list(tokenize("${{ len(keys(abc)) }}")))


def test_func_call_multiple_args() -> None:
    assert [
        Call(FUNCTIONS["fmt"], [Literal("{} {}"), Literal("abc"), Literal(123)], [])
    ] == PARSER.parse(list(tokenize('${{ fmt("{} {}", "abc", 123) }}')))


def test_func_call_arg_lookup() -> None:
    assert [
        Call(
            FUNCTIONS["len"],
            [Lookup("images", [AttrGetter("name"), AttrGetter("build_args")])],
            [],
        )
    ] == PARSER.parse(list(tokenize("${{ len(images.name.build_args) }}")))


def test_func_call_with_trailer_attr() -> None:
    assert [
        Call(
            FUNCTIONS["from_json"],
            [Literal('{"a": 1, "b": "val"}')],
            [AttrGetter("a")],
        )
    ] == PARSER.parse(list(tokenize("""${{ from_json('{"a": 1, "b": "val"}').a }}""")))


def test_func_call_with_trailer_item() -> None:
    assert [
        Call(
            FUNCTIONS["from_json"],
            [Literal('{"a": 1, "b": "val"}')],
            [ItemGetter(Literal("a"))],
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
                dedent(
                    """\
                        jupyter notebook
                          --no-browser
                          --ip=0.0.0.0
                          --allow-root
                          --NotebookApp.token=
                          --notebook-dir="""
                )
            ),
            Lookup("volumes", [AttrGetter("notebooks"), AttrGetter("mount")]),
            Text("\n"),
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
        Text("bash -c 'cd "),
        Lookup("volumes", [AttrGetter(name="project"), AttrGetter(name="mount")]),
        Text(" &&\n  python -u "),
        Lookup("volumes", [AttrGetter(name="code"), AttrGetter(name="mount")]),
        Text("/train.py\n    --data "),
        Lookup("volumes", [AttrGetter(name="data"), AttrGetter(name="mount")]),
        Text("'\n"),
    ] == PARSER.parse(list(tokenize(s)))
