from neuro_flow.expr import Token, tokenize


def test_empty() -> None:
    assert [] == list(tokenize(""))


def test_non_template() -> None:
    assert [Token("TEXT", "abc def   jik")] == list(tokenize("abc def   jik"))


def test_non_template_with_unknown_chars() -> None:
    assert [Token("TEXT", "abc!jik")] == list(tokenize("abc!jik"))


def test_template() -> None:
    assert [
        Token("TEXT", "abc "),
        Token("LTMPL", "${{"),
        Token("NAME", "job"),
        Token("DOT", "."),
        Token("NAME", "job-id"),
        Token("DOT", "."),
        Token("NAME", "name"),
        Token("RTMPL", "}}"),
        Token("TEXT", "jik"),
    ] == list(tokenize("abc ${{ job.job-id.name }}jik"))
