from neuro_flow.expr import Token, tokenize


def test_empty() -> None:
    assert [] == list(tokenize(""))


def test_non_template() -> None:
    assert [
        Token("NAME", "abc"),
        Token("SPACE", " "),
        Token("NAME", "def"),
        Token("SPACE", "   "),
        Token("NAME", "jik"),
    ] == list(tokenize("abc def   jik"))


def test_non_template_with_unknown_chars() -> None:
    assert [Token("NAME", "abc"), Token("ANY", "!"), Token("NAME", "jik")] == list(
        tokenize("abc!jik")
    )


def test_template() -> None:
    assert [
        Token("NAME", "abc"),
        Token("SPACE", " "),
        Token("TMPL", "${{"),
        Token("SPACE", " "),
        Token("NAME", "job"),
        Token("DOT", "."),
        Token("NAME", "job-id"),
        Token("DOT", "."),
        Token("NAME", "name"),
        Token("SPACE", " "),
        Token("TMPL", "}}"),
        Token("NAME", "jik"),
    ] == list(tokenize("abc ${{ job.job-id.name }}jik"))
