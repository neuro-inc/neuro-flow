import pytest
from funcparserlib.parser import NoParseError, Parser

from neuro_flow.expr import PARSER, TEXT, TMPL, Lookup, Text, finished, skip, tokenize


def finish(p: Parser) -> Parser:
    return p + skip(finished)


def test_tmpl_ok1() -> None:
    assert Lookup(names=["name"]) == finish(TMPL).parse(list(tokenize("${{ name }}")))


def test_tmpl_ok2() -> None:
    assert Lookup(names=["name", "sub", "param"]) == finish(TMPL).parse(
        list(tokenize("${{ name.sub.param }}"))
    )


def test_tmpl_ok3() -> None:
    assert Lookup(names=["name"]) == finish(TMPL).parse(list(tokenize("${{name}}")))


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


def test_tmpl_literal_none() -> None:
    assert finish(TMPL).parse(list(tokenize("${{ None }}"))) is None


def test_tmpl_literal_real() -> None:
    assert 12.34 == finish(TMPL).parse(list(tokenize("${{ 12.34 }}")))


def test_tmpl_literal_exp() -> None:
    assert -12.34e-21 == finish(TMPL).parse(list(tokenize("${{ -12.34e-21 }}")))


def test_tmpl_literal_int1() -> None:
    assert 1234 == finish(TMPL).parse(list(tokenize("${{ 1234 }}")))


def test_tmpl_literal_int2() -> None:
    assert 1234 == finish(TMPL).parse(list(tokenize("${{ 12_34 }}")))


def test_tmpl_literal_int3() -> None:
    assert -1234 == finish(TMPL).parse(list(tokenize("${{ -1234 }}")))


def test_tmpl_literal_hex1() -> None:
    assert 0x12AB == finish(TMPL).parse(list(tokenize("${{ 0x12ab }}")))


def test_tmpl_literal_hex2() -> None:
    assert 0x12AB == finish(TMPL).parse(list(tokenize("${{ 0X12_ab }}")))


def test_tmpl_literal_oct1() -> None:
    assert 0o1234 == finish(TMPL).parse(list(tokenize("${{ 0o1234 }}")))


def test_tmpl_literal_oct2() -> None:
    assert 0o1234 == finish(TMPL).parse(list(tokenize("${{ 0O12_34 }}")))


def test_tmpl_literal_bin1() -> None:
    assert 0b0110 == finish(TMPL).parse(list(tokenize("${{ 0b0110 }}")))


def test_tmpl_literal_bin2() -> None:
    assert 0b0110 == finish(TMPL).parse(list(tokenize("${{ 0B01_10 }}")))


def test_tmpl_literal_bool1() -> None:
    assert finish(TMPL).parse(list(tokenize("${{ True }}"))) is True


def test_tmpl_literal_bool2() -> None:
    assert finish(TMPL).parse(list(tokenize("${{ False }}"))) is False


def test_tmpl_literal_str1() -> None:
    assert "str" == finish(TMPL).parse(list(tokenize("${{ 'str' }}")))


def test_tmpl_literal_str2() -> None:
    assert "abc\tdef" == finish(TMPL).parse(list(tokenize("${{ 'abc\tdef' }}")))


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
    assert [Text("some "), Lookup(["var", "arg"]), Text(" text")] == PARSER.parse(
        list(tokenize("some ${{ var.arg }} text"))
    )
