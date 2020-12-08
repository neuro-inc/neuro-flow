import dataclasses

import re
from typing import Iterator, Optional

from .types import LocalPath


@dataclasses.dataclass(frozen=True)
class Pos:
    line: int
    col: int
    filename: LocalPath


@dataclasses.dataclass(frozen=True)
class Token:
    type: str
    value: str
    start: Pos
    end: Pos

    def _pos_str(self) -> str:
        sl, sp = self.start.line, self.start.col
        el, ep = self.end.line, self.end.col
        return "%d,%d-%d,%d:" % (sl, sp, el, ep)

    def __str__(self) -> str:
        s = f"{self._pos_str()} {self.type} '{self.value}'"
        return s.strip()

    @property
    def name(self) -> str:
        return self.value

    def pformat(self) -> str:
        return "{} {} '{}'".format(
            self._pos_str().ljust(20),
            self.type.ljust(14),
            self.value,
        )


class LexerError(Exception):
    def __init__(self, place: Pos, msg: str) -> None:
        self.place = place
        self.msg = msg

    def __str__(self) -> str:
        s = "cannot tokenize data"
        return f'{s}: {self.place.line},{self.place.col}: "{self.msg}"'


class Tokenizer:

    TOKENS = [
        ("LTMPL", r"\$\{\{"),
        ("RTMPL", r"\}\}"),
        ("LTMPL2", r"\$\[\["),
        ("RTMPL2", r"\]\]"),
        ("SPACE", r"[ \t]+"),
        ("NONE", r"None"),
        ("BOOL", r"True|False"),
        ("REAL", r"-?[0-9]+\.[0-9]*([Ee][+\-]?[0-9]+)*"),
        ("EXP", r"-?[0-9]+\.[0-9]*([Ee][+\-]?[0-9]+)*[+\-]?e[0-9]+"),
        ("HEX", r"0[xX][0-9a-fA-F_]+"),
        ("OCT", r"0[oO][0-7_]+"),
        ("BIN", r"0[bB][0-1_]+"),
        ("INT", r"-?[0-9][0-9_]*"),
        ("STR", r"'[^']*'|" r'"[^"]*"'),
        ("OP", r"(==|!=|or|and|<=|<|>=|>|\||\+|-|\*|/)(?=[ \t])"),
        ("UNARY_OP", r"(not)(?=[ \t])"),
        ("NAME", r"[A-Za-z][A-Za-z_0-9]*"),
        ("DOT", r"\."),
        ("COMMA", r","),
        ("COLON", r":"),
        ("LPAR", r"\("),
        ("RPAR", r"\)"),
        ("LSQB", r"\["),
        ("RSQB", r"\]"),
        ("LBRACE", r"\{"),
        ("RBRACE", r"\}"),
    ]
    TOKENS_RE = re.compile("|".join(f"(?P<{typ}>{regexp})" for typ, regexp in TOKENS))

    LTMPL_RE = re.compile(r"\$\{\{|\$\[\[")
    RTMPL_RE = re.compile(r"\}\}|\]\]")

    def make_token(self, typ: str, value: str, pos: Pos) -> Token:
        nls = value.count("\n")
        n_line = pos.line + nls
        if nls == 0:
            n_col = pos.col + len(value)
        else:
            n_col = len(value) - value.rfind("\n") - 1
        return Token(typ, value, pos, Pos(n_line, n_col, pos.filename))

    def match_specs(self, s: str, i: int, start: Pos, pos: Pos) -> Token:
        m = self.TOKENS_RE.match(s, i)
        if m is not None:
            assert m.lastgroup
            return self.make_token(m.lastgroup, m.group(), pos)
        else:
            errline = s.splitlines()[pos.line - start.line]
            raise LexerError(pos, " " * start.col + errline)

    def match_text(self, s: str, i: int, start: Pos, pos: Pos) -> Optional[Token]:
        ltmpl = self.LTMPL_RE.search(s, i)
        if ltmpl is None:
            idx = len(s)
        else:
            if ltmpl.start() == i:
                return None
            else:
                idx = ltmpl.start()
        rtmpl = self.RTMPL_RE.search(s, i, idx)
        if rtmpl is not None:
            t = self.make_token("TEXT", s[i : rtmpl.start()], pos)
            errline = s.splitlines()[t.end.line - start.line]
            raise LexerError(t.end, " " * start.col + errline)
        return self.make_token("TEXT", s[i:idx], pos)

    def __call__(self, s: str, start: Pos) -> Iterator[Token]:
        in_expr = False
        length = len(s)
        pos = start
        i = 0
        while i < length:
            if in_expr:
                t = self.match_specs(s, i, start, pos)
                if t.type in ("RTMPL", "RTMPL2"):
                    in_expr = False
            else:
                txt = self.match_text(s, i, start, pos)
                if txt is None:
                    in_expr = True
                    t = self.match_specs(s, i, start, pos)
                else:
                    t = txt
            if t.type != "SPACE":
                yield t
            pos = t.end
            i += len(t.value)


tokenize = Tokenizer()
