# expression parser/evaluator

# ${{ <expression> }}

import dataclasses
from ast import literal_eval
from typing import Any, List, Sequence, Tuple

from funcparserlib.lexer import Token, make_tokenizer
from funcparserlib.parser import Parser, a, finished, many, maybe, oneplus, skip, some


TOKENS = [
    ("TMPL", (r"\$\{\{|\}\}",)),
    ("SPACE", (r"[ \t]+",)),
    ("NONE", (r"None",)),
    ("BOOL", (r"True|False",)),
    ("REAL", (r"-?[0-9]+\.[0-9]*([Ee][+\-]?[0-9]+)*",)),
    ("EXP", (r"-?[0-9]+\.[0-9]*([Ee][+\-]?[0-9]+)*[+\-]?e[0-9]+",)),
    ("HEX", (r"0[xX][0-9a-fA-F_]+",)),
    ("OCT", (r"0[oO][0-7_]+",)),
    ("BIN", (r"0[bB][0-1_]+",)),
    ("INT", (r"-?[0-9][0-9_]*",)),
    ("STR", (r"'[^']*'",)),
    ("NAME", (r"[A-Za-z_][A-Za-z_0-9\-]*",)),
    ("DOT", (r"\.",)),
    ("ANY", (r".",)),
]


tokenize = make_tokenizer(TOKENS)


def tokval(tok: Token) -> str:
    return tok.value


def literal(toktype: str) -> Parser:
    def f(tok: Token) -> Any:
        return literal_eval(tokval(tok))

    return some(lambda tok: tok.type == toktype) >> f


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

REAL = literal("REAL")

EXP = literal("EXP")

INT = literal("INT")

HEX = literal("HEX")

OCT = literal("OCT")

BIN = literal("BIN")

BOOL = literal("BOOL")

STR = literal("STR")

NONE = literal("NONE")

LITERAL = REAL | EXP | INT | HEX | OCT | BIN | BOOL | STR | NONE

NAME = some(lambda tok: tok.type == "NAME") >> tokval

LOOKUP = NAME + many(DOT + NAME) >> make_lookup

EXPR = LITERAL | LOOKUP

TMPL = OPEN_TMPL + skip(maybe(SPACE)) + EXPR + skip(maybe(SPACE)) + CLOSE_TMPL

TEXT = oneplus(NOT_TMPL) >> (lambda arg: Text("".join(arg)))

PARSER = oneplus(TMPL | TEXT) + skip(finished)


class Expr:
    def __init__(self, pattern: str) -> None:
        tokens = list(tokenize(pattern))
        self._pattern = tuple(PARSER.parse(tokens))

    # def eval(self, contexts) -> str:
    #     pass
