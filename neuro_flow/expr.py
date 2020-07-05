# expression parser/evaluator

import abc
import dataclasses

# ${{ <expression> }}
import inspect
from ast import literal_eval
from pathlib import Path, PurePosixPath
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    cast,
)

from funcparserlib.lexer import Token, make_tokenizer
from funcparserlib.parser import (
    Parser,
    a,
    finished,
    forward_decl,
    many,
    maybe,
    oneplus,
    skip,
    some,
)
from yarl import URL


_T = TypeVar("_T")
_E = TypeVar("_E")


Literal = Union[None, bool, int, float, str]


class LookupABC(abc.ABC):
    @abc.abstractmethod
    def lookup(self, names: Sequence[str]) -> Literal:
        pass


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
    ("STR", (r'"[^"]*"',)),
    ("NAME", (r"[A-Za-z_][A-Za-z_0-9\-]*",)),
    ("DOT", (r"\.",)),
    ("COMMA", (r",",)),
    ("PAR", (r"\(|\)",)),
    ("SQB", (r"\[|\]",)),
    ("ANY", (r".",)),
]


tokenize = make_tokenizer(TOKENS)


@dataclasses.dataclass(frozen=True)
class FuncDef:
    name: str
    sig: inspect.Signature
    call: Callable[..., Awaitable[Any]]


def _build_signatures(**kwargs: Callable[..., Any]) -> Dict[str, FuncDef]:
    return {k: FuncDef(k, inspect.signature(v), v) for k, v in kwargs.items()}


async def nothing() -> None:
    # A test function that accepts none args.
    # Later we can replace it with something really more usefuld, e.g. succeded()
    return None


async def alen(arg: Any) -> int:
    # Async version of len(), async is required for the sake of uniformness.
    return len(arg)


async def fmt(spec: str, *args: Any) -> str:
    # We need a trampoline since expression syntax doesn't support classes and named
    # argumens
    return spec.format(*args)


FUNCTIONS = _build_signatures(len=alen, nothing=nothing, fmt=fmt)


def tokval(tok: Token) -> str:
    return cast(str, tok.value)


def literal(toktype: str) -> Parser:
    def f(tok: Token) -> Any:
        return literal_eval(tokval(tok))

    return some(lambda tok: tok.type == toktype) >> f


class Item(abc.ABC):
    @abc.abstractmethod
    async def eval(self, lookuper: LookupABC) -> str:
        pass


@dataclasses.dataclass(frozen=True)
class Lookup(Item):
    names: Sequence[str]

    async def eval(self, lookuper: LookupABC) -> str:
        return ".".join(self.names)


def make_lookup(arg: Tuple[str, List[str]]) -> Lookup:
    return Lookup([arg[0]] + arg[1])


@dataclasses.dataclass(frozen=True)
class Call(Item):
    func: FuncDef
    args: Sequence[Item]

    async def eval(self, lookuper: LookupABC) -> str:
        args = [await a.eval(lookuper) for a in self.args]
        return await self.func(*args)


def make_args(arg: Optional[Tuple[Any, List[Any]]]) -> List[Any]:
    if arg is None:
        return []
    first, tail = arg
    return [first] + tail[:]


def make_call(arg: Tuple[str, List[str]]) -> Call:
    funcname, args = arg
    try:
        spec = FUNCTIONS[funcname]
    except KeyError:
        raise LookupError(f"Unknown function {funcname}")
    args_count = len(args)
    dummies = [None] * args_count
    spec.sig.bind(*dummies)
    return Call(spec, args)


@dataclasses.dataclass(frozen=True)
class Text(Item):
    arg: str

    async def eval(self, lookuper: LookupABC) -> str:
        return self.arg


SPACE = some(lambda tok: tok.type == "SPACE")
OPT_SPACE = skip(maybe(SPACE))

DOT = skip(a(Token("DOT", ".")))
COMMA = skip(a(Token("COMMA", ",")))

OPEN_TMPL = skip(a(Token("TMPL", "${{")))
CLOSE_TMPL = skip(a(Token("TMPL", "}}")))

NOT_TMPL = some(lambda tok: tok.type != "TMPL") >> tokval

LPAR = skip(a(Token("PAR", "(")))
RPAR = skip(a(Token("PAR", ")")))

LSQB = skip(a(Token("PAR", "[")))
RSQB = skip(a(Token("PAR", "]")))

REAL = literal("REAL") | literal("EXP")

INT = literal("INT") | literal("HEX") | literal("OCT") | literal("BIN")

BOOL = literal("BOOL")

STR = literal("STR")

NONE = literal("NONE")

LITERAL = NONE | BOOL | REAL | INT | STR

NAME = some(lambda tok: tok.type == "NAME") >> tokval

LOOKUP = NAME + many(DOT + NAME) >> make_lookup

SIMPLE_EXPR = LITERAL | LOOKUP

EXPR = forward_decl()

FUNC_CALL = (
    NAME
    + OPT_SPACE
    + LPAR
    + OPT_SPACE
    + (
        maybe(EXPR + many(OPT_SPACE + COMMA + OPT_SPACE + EXPR) + OPT_SPACE)
        >> make_args
    )
    + RPAR
) >> make_call


EXPR.define(FUNC_CALL | SIMPLE_EXPR)


TMPL = OPEN_TMPL + OPT_SPACE + EXPR + OPT_SPACE + CLOSE_TMPL

TEXT = oneplus(NOT_TMPL) >> (lambda arg: Text("".join(arg)))

PARSER = oneplus(TMPL | TEXT) + skip(finished)


class Expr(Generic[_T]):
    allow_none = True

    @classmethod
    def convert(cls, arg: str) -> _T:
        # implementation for StrExpr and OptStrExpr
        return cast(_T, arg)

    def __init__(self, pattern: Optional[str]) -> None:
        self._pattern = pattern
        # precalculated value for constant string, allows raising errors earlier
        self._ret: Optional[_T] = None
        if pattern is not None:
            tokens = list(tokenize(pattern))
            self._parsed: Optional[Sequence[Item]] = PARSER.parse(tokens)
            assert self._parsed is not None
            if len(self._parsed) == 1 and type(self._parsed[0]) == Text:
                self._ret = self.convert(cast(Text, self._parsed[0]).arg)
        elif self.allow_none:
            self._parsed = None
        else:
            raise TypeError("None is not allowed")

    @property
    def pattern(self) -> Optional[str]:
        return self._pattern

    async def eval(self, lookuper: LookupABC) -> Optional[_T]:
        if self._ret is not None:
            return self._ret
        if self._parsed is not None:
            ret: List[str] = []
            for part in self._parsed:
                ret.append(await part.eval(lookuper))
            return self.convert("".join(ret))
        else:
            if not self.allow_none:
                # Dead code, a error for None is raised by __init__()
                # The check is present for better readability.
                raise ValueError("Expression is calculated to None")
            return None

    def __repr__(self) -> str:
        return f"{self.__class__.__qualname__}({self._pattern})"

    def __eq__(self, other: Any) -> bool:
        if type(self) != type(other):
            return False
        assert isinstance(other, self.__class__)
        return self._pattern == other._pattern

    def __hash__(self) -> int:
        return hash((self.__class__.__name__, self._pattern))


class StrictExpr(Expr[Optional[_T]]):
    allow_none = False

    async def eval(self, lookuper: LookupABC) -> _T:
        ret = await super().eval(lookuper)
        assert ret is not None
        return ret


# These comprehensive specializations exist mainly for static type checker


class StrExpr(StrictExpr[str]):
    pass


class OptStrExpr(Expr[str]):
    pass


class URIExprMixin:
    @classmethod
    def convert(cls, arg: str) -> URL:
        return URL(arg)


class URIExpr(URIExprMixin, StrictExpr[URL]):
    pass


class OptURIExpr(URIExprMixin, Expr[URL]):
    pass


class BoolExprMixin:
    @classmethod
    def convert(cls, arg: str) -> bool:
        return bool(literal_eval(arg))


class BoolExpr(BoolExprMixin, StrictExpr[bool]):
    pass


class OptBoolExpr(BoolExprMixin, Expr[bool]):
    pass


class IntExpr(StrictExpr[int]):
    @classmethod
    def convert(cls, arg: str) -> int:
        return int(literal_eval(arg))


class FloatExprMixin:
    @classmethod
    def convert(cls, arg: str) -> float:
        return float(literal_eval(arg))


class FloatExpr(FloatExprMixin, StrictExpr[float]):
    pass


class OptFloatExpr(FloatExprMixin, Expr[float]):
    pass


class LocalPathMixin:
    @classmethod
    def convert(cls, arg: str) -> Path:
        return Path(arg)


class LocalPathExpr(LocalPathMixin, StrictExpr[Path]):
    pass


class OptLocalPathExpr(LocalPathMixin, Expr[Path]):
    pass


class RemotePathMixin:
    @classmethod
    def convert(cls, arg: str) -> PurePosixPath:
        return PurePosixPath(arg)


class RemotePathExpr(RemotePathMixin, StrictExpr[PurePosixPath]):
    pass


class OptRemotePathExpr(RemotePathMixin, Expr[PurePosixPath]):
    pass
