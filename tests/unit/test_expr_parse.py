import pytest
from funcparserlib.parser import NoParseError, Parser

from neuro_flow.expr import PARSER, TEXT, TMPL, Lookup, Text, finished, skip, tokenize


def finish(p: Parser) -> Parser:
    return p + skip(finished)


def test_tmpl_ok1() -> None:
    assert Lookup(names=("name",)) == finish(TMPL).parse(list(tokenize("${{ name }}")))


def test_tmpl_ok2() -> None:
    assert Lookup(names=("name", "sub", "param")) == finish(TMPL).parse(
        list(tokenize("${{ name.sub.param }}"))
    )


def test_tmpl_ok3() -> None:
    assert Lookup(names=("name",)) == finish(TMPL).parse(list(tokenize("${{name}}")))


def test_tmpl_false1() -> None:
    with pytest.raises(NoParseError):
        finish(TMPL).parse(list(tokenize("name.sub.param")))


def test_tmpl_false2() -> None:
    with pytest.raises(NoParseError):
        finish(TMPL).parse(list(tokenize("name sub  param")))


def test_tmpl_false3() -> None:
    with pytest.raises(NoParseError):
        finish(TMPL).parse(list(tokenize("${{ name sub  param")))


def test_tmpl_false4() -> None:
    with pytest.raises(NoParseError):
        finish(TMPL).parse(list(tokenize("${{ name")))


def test_tmpl_false5() -> None:
    with pytest.raises(NoParseError):
        finish(TMPL).parse(list(tokenize("name }}")))


def test_text_ok() -> None:
    assert Text("some text") == finish(TEXT).parse(list(tokenize("some text")))


def test_text_false1() -> None:
    with pytest.raises(NoParseError):
        assert [] == finish(TEXT).parse(list(tokenize("${{")))


def test_text_false2() -> None:
    with pytest.raises(NoParseError):
        finish(TEXT).parse(list(tokenize("${{ name")))


def test_text_false3() -> None:
    with pytest.raises(NoParseError):
        finish(TEXT).parse(list(tokenize("${{ name }}")))


def test_text_false4() -> None:
    with pytest.raises(NoParseError):
        finish(TEXT).parse(list(tokenize("name }}")))


def test_parser1() -> None:
    assert [Text("some "), Lookup(("var", "arg")), Text(" text")] == PARSER.parse(
        list(tokenize("some ${{ var.arg }} text"))
    )
