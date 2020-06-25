# expression parser/evaluator

# ${{ <expression> }}

import dataclasses
from typing import List, Sequence, Tuple

from funcparserlib.lexer import Token, make_tokenizer
from funcparserlib.parser import a, finished, many, maybe, oneplus, skip, some


TOKENS = [
    ("TMPL", (r"\$\{\{|\}\}",)),
    ("SPACE", (r"[ \t]+",)),
    ("NAME", (r"[A-Za-z_][A-Za-z_0-9\-]*",)),
    ("DOT", (r"\.",)),
    ("ANY", (r".",)),
    # ('REAL', (r'[0-9]+\.[0-9]*([Ee][+\-]?[0-9]+)*',)),
    # ('INT', (r'[0-9]+',)),
]


tokenize = make_tokenizer(TOKENS)


def tokval(tok: Token) -> str:
    return tok.value


@dataclasses.dataclass(frozen=True)
class Lookup:
    names: Sequence[str]


@dataclasses.dataclass(frozen=True)
class Text:
    arg: str


def make_lookup(arg: Tuple[str, List[str]]) -> Lookup:
    return Lookup(tuple([arg[0]] + arg[1]))


SPACE = some(lambda tok: tok.type == "SPACE")

DOT = skip(a(Token("DOT", ".")))

OPEN_TMPL = skip(a(Token("TMPL", "${{")))

CLOSE_TMPL = skip(a(Token("TMPL", "}}")))

NOT_TMPL = some(lambda tok: tok.type != "TMPL") >> tokval

NAME = some(lambda tok: tok.type == "NAME") >> tokval

LOOKUP = NAME + many(DOT + NAME) >> make_lookup

TMPL = OPEN_TMPL + skip(maybe(SPACE)) + LOOKUP + skip(maybe(SPACE)) + CLOSE_TMPL

TEXT = oneplus(NOT_TMPL) >> (lambda arg: Text("".join(arg)))

PARSER = oneplus(TMPL | TEXT) + skip(finished)


class Expr:
    def __init__(self, pattern: str) -> None:
        tokens = list(tokenize(pattern))
        self._pattern = tuple(PARSER.parse(tokens))

    # def eval(self, contexts) -> str:
    #     pass
