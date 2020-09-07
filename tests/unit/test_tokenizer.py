from neuro_flow.tokenizer import Pos, Token, tokenize
from neuro_flow.types import LocalPath


def test_empty() -> None:
    assert [] == list(tokenize("", Pos(0, 0, LocalPath("<test>"))))


def test_non_template() -> None:
    assert [
        Token(
            "TEXT",
            "abc def   jik",
            Pos(0, 0, LocalPath("<test>")),
            Pos(0, 13, LocalPath("<test>")),
        )
    ] == list(tokenize("abc def   jik", Pos(0, 0, LocalPath("<test>"))))


def test_non_template_with_unknown_chars() -> None:
    assert [
        Token(
            "TEXT",
            "abc!jik",
            Pos(0, 0, LocalPath("<test>")),
            Pos(0, 7, LocalPath("<test>")),
        )
    ] == list(tokenize("abc!jik", Pos(0, 0, LocalPath("<test>"))))


def test_template_curly() -> None:
    assert [
        Token(
            "TEXT",
            "abc ",
            Pos(0, 0, LocalPath("<test>")),
            Pos(0, 4, LocalPath("<test>")),
        ),
        Token(
            "LTMPL",
            "${{",
            Pos(0, 4, LocalPath("<test>")),
            Pos(0, 7, LocalPath("<test>")),
        ),
        Token(
            "NAME",
            "job",
            Pos(0, 8, LocalPath("<test>")),
            Pos(0, 11, LocalPath("<test>")),
        ),
        Token(
            "DOT", ".", Pos(0, 11, LocalPath("<test>")), Pos(0, 12, LocalPath("<test>"))
        ),
        Token(
            "NAME",
            "job_id",
            Pos(0, 12, LocalPath("<test>")),
            Pos(0, 18, LocalPath("<test>")),
        ),
        Token(
            "DOT", ".", Pos(0, 18, LocalPath("<test>")), Pos(0, 19, LocalPath("<test>"))
        ),
        Token(
            "NAME",
            "name",
            Pos(0, 19, LocalPath("<test>")),
            Pos(0, 23, LocalPath("<test>")),
        ),
        Token(
            "RTMPL",
            "}}",
            Pos(0, 24, LocalPath("<test>")),
            Pos(0, 26, LocalPath("<test>")),
        ),
        Token(
            "TEXT",
            "jik",
            Pos(0, 26, LocalPath("<test>")),
            Pos(0, 29, LocalPath("<test>")),
        ),
    ] == list(tokenize("abc ${{ job.job_id.name }}jik", Pos(0, 0, LocalPath("<test>"))))


def test_template_square() -> None:
    assert [
        Token(
            "TEXT",
            "abc ",
            Pos(0, 0, LocalPath("<test>")),
            Pos(0, 4, LocalPath("<test>")),
        ),
        Token(
            "LTMPL2",
            "$[[",
            Pos(0, 4, LocalPath("<test>")),
            Pos(0, 7, LocalPath("<test>")),
        ),
        Token(
            "NAME",
            "job",
            Pos(0, 8, LocalPath("<test>")),
            Pos(0, 11, LocalPath("<test>")),
        ),
        Token(
            "DOT", ".", Pos(0, 11, LocalPath("<test>")), Pos(0, 12, LocalPath("<test>"))
        ),
        Token(
            "NAME",
            "job_id",
            Pos(0, 12, LocalPath("<test>")),
            Pos(0, 18, LocalPath("<test>")),
        ),
        Token(
            "DOT", ".", Pos(0, 18, LocalPath("<test>")), Pos(0, 19, LocalPath("<test>"))
        ),
        Token(
            "NAME",
            "name",
            Pos(0, 19, LocalPath("<test>")),
            Pos(0, 23, LocalPath("<test>")),
        ),
        Token(
            "RTMPL2",
            "]]",
            Pos(0, 24, LocalPath("<test>")),
            Pos(0, 26, LocalPath("<test>")),
        ),
        Token(
            "TEXT",
            "jik",
            Pos(0, 26, LocalPath("<test>")),
            Pos(0, 29, LocalPath("<test>")),
        ),
    ] == list(tokenize("abc $[[ job.job_id.name ]]jik", Pos(0, 0, LocalPath("<test>"))))
