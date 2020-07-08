# expression parser/evaluator
# ${{ <expression> }}

import abc
import dataclasses
import inspect
import re
from ast import literal_eval
from collections.abc import Sized
from pathlib import Path, PurePosixPath
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Generic,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    cast,
)

from funcparserlib.lexer import LexerError, Token
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
from typing_extensions import Protocol, runtime_checkable
from yarl import URL


_T = TypeVar("_T")


LiteralT = Union[None, bool, int, float, str]

TypeT = Union[LiteralT, "ContainerT", "MappingT", "SequenceT"]


@runtime_checkable
class ContainerT(Protocol):
    def __getattr__(self, attr: str) -> TypeT:
        ...


@runtime_checkable
class MappingT(Protocol):
    def __getitem__(self, key: LiteralT) -> TypeT:
        ...


@runtime_checkable
class SequenceT(Protocol):
    def __getitem__(self, idx: LiteralT) -> TypeT:
        ...


class RootABC(abc.ABC):
    @abc.abstractmethod
    def lookup(self, name: str) -> TypeT:
        pass


def make_tokenizer() -> Callable[[str], Iterator[Token]]:

    TOKENS = [
        ("LTMPL", re.compile(r"\$\{\{")),
        ("RTMPL", re.compile(r"\}\}")),
        ("SPACE", re.compile(r"[ \t]+")),
        ("NONE", re.compile(r"None")),
        ("BOOL", re.compile(r"True|False")),
        ("REAL", re.compile(r"-?[0-9]+\.[0-9]*([Ee][+\-]?[0-9]+)*")),
        ("EXP", re.compile(r"-?[0-9]+\.[0-9]*([Ee][+\-]?[0-9]+)*[+\-]?e[0-9]+")),
        ("HEX", re.compile(r"0[xX][0-9a-fA-F_]+")),
        ("OCT", re.compile(r"0[oO][0-7_]+")),
        ("BIN", re.compile(r"0[bB][0-1_]+")),
        ("INT", re.compile(r"-?[0-9][0-9_]*")),
        ("STR", re.compile(r"'[^']*'")),
        ("STR", re.compile(r'"[^"]*"')),
        ("NAME", re.compile(r"[A-Za-z_][A-Za-z_0-9\-]*")),
        ("DOT", re.compile(r"\.")),
        ("COMMA", re.compile(r",")),
        ("LPAR", re.compile(r"\(")),
        ("RPAR", re.compile(r"\)")),
        ("LSQB", re.compile(r"\[")),
        ("RSQB", re.compile(r"\]")),
    ]

    def make_token(typ: str, value: str, line: int, pos: int) -> Token:
        nls = value.count("\n")
        n_line = line + nls
        if nls == 0:
            n_pos = pos + len(value)
        else:
            n_pos = len(value) - value.rfind("\n") - 1
        return Token(typ, value, (line, pos + 1), (n_line, n_pos))

    def match_specs(s: str, i: int, position: Tuple[int, int]) -> Token:
        line, pos = position
        for typ, regexp in TOKENS:
            m = regexp.match(s, i)
            if m is not None:
                return make_token(typ, m.group(), line, pos)
        else:
            errline = s.splitlines()[line - 1]
            raise LexerError((line, pos + 1), errline)

    def match_text(s: str, i: int, position: Tuple[int, int]) -> Token:
        ltmpl = s.find("${{", i)
        if ltmpl == i:
            return None
        if ltmpl == -1:
            # LTMPL not found, use the whole string
            substr = s[i:]
        else:
            substr = s[i:ltmpl]
        line, pos = position
        if "}}" in substr:
            errline = s.splitlines()[line - 1]
            raise LexerError((line, pos + 1), errline)
        return make_token("TEXT", substr, line, pos)

    def f(s: str) -> Iterator[Token]:
        in_expr = False
        length = len(s)
        line, pos = 1, 0
        i = 0
        while i < length:
            if in_expr:
                t = match_specs(s, i, (line, pos))
                if t.type == "RTMPL":
                    in_expr = False
            else:
                t = match_text(s, i, (line, pos))
                if not t:
                    in_expr = True
                    t = match_specs(s, i, (line, pos))
            if t.type != "SPACE":
                yield t
            line, pos = t.end
            i += len(t.value)

    return f


tokenize = make_tokenizer()


@dataclasses.dataclass(frozen=True)
class FuncDef:
    name: str
    sig: inspect.Signature
    call: Callable[..., Awaitable[TypeT]]


def _build_signatures(**kwargs: Callable[..., Awaitable[TypeT]]) -> Dict[str, FuncDef]:
    return {k: FuncDef(k, inspect.signature(v), v) for k, v in kwargs.items()}


async def nothing(root: RootABC) -> None:
    # A test function that accepts none args.
    # Later we can replace it with something really more usefuld, e.g. succeded()
    return None


async def alen(root: RootABC, arg: TypeT) -> int:
    # Async version of len(), async is required for the sake of uniformness.
    if not isinstance(arg, Sized):
        raise TypeError(f"len() requires a str, sequence or mapping, got {arg!r}")
    return len(arg)


async def akeys(root: RootABC, arg: TypeT) -> TypeT:
    # Async version of len(), async is required for the sake of uniformness.
    if not isinstance(arg, Mapping):
        raise TypeError(f"keys() requires a mapping, got {arg!r}")
    return list(arg)  # type: ignore  # List[...] is implicitly converted to SequenceT


async def fmt(root: RootABC, spec: str, *args: TypeT) -> str:
    # We need a trampoline since expression syntax doesn't support classes and named
    # argumens
    return spec.format(*args)


FUNCTIONS = _build_signatures(len=alen, nothing=nothing, fmt=fmt, keys=akeys)


def tokval(tok: Token) -> str:
    return cast(str, tok.value)


class Item(abc.ABC):
    @abc.abstractmethod
    async def eval(self, root: RootABC) -> TypeT:
        pass


@dataclasses.dataclass(frozen=True)
class Literal(Item):
    val: LiteralT

    async def eval(self, root: RootABC) -> LiteralT:
        return self.val


def literal(toktype: str) -> Parser:
    def f(tok: Token) -> Any:
        return Literal(literal_eval(tokval(tok)))

    return some(lambda tok: tok.type == toktype) >> f


class Getter(abc.ABC):
    # Aux class for Lookup item

    @abc.abstractmethod
    def __call__(self, obj: TypeT, prefix: str) -> Tuple[TypeT, str]:
        pass


@dataclasses.dataclass(frozen=True)
class AttrGetter(Getter):
    name: str

    def __call__(self, obj: TypeT, prefix: str) -> Tuple[TypeT, str]:
        if dataclasses.is_dataclass(obj):
            name = self.name.replace("-", "_")
            try:
                return cast(TypeT, getattr(obj, name)), prefix + "." + self.name
            except AttributeError:
                raise AttributeError(f"{prefix} has no attribute {self.name}")
        elif isinstance(obj, MappingT):
            try:
                return obj[self.name], prefix + "." + self.name
            except KeyError:
                raise AttributeError(f"{prefix} has no attribute {self.name}")
        else:
            raise TypeError(
                f"{prefix} is not an object with attributes accessible by a dot."
            )


def lookup_attr(name: str) -> Any:
    # Just in case, NAME token cannot start with _.
    assert not name.startswith(("_", "-"))
    return AttrGetter(name)


@dataclasses.dataclass(frozen=True)
class ItemGetter(Getter):
    key: LiteralT

    def __call__(self, obj: TypeT, prefix: str) -> Tuple[TypeT, str]:
        assert isinstance(obj, (SequenceT, MappingT))
        return obj[self.key], prefix + "[" + str(self.key) + "]"


def lookup_item(key: LiteralT) -> Any:
    return ItemGetter(key)


@dataclasses.dataclass(frozen=True)
class Lookup(Item):
    root: str
    trailer: Sequence[Getter]

    async def eval(self, root: RootABC) -> TypeT:
        ret = root.lookup(self.root)
        prefix = self.root
        for op in self.trailer:
            ret, prefix = op(ret, prefix)
        return ret


def make_lookup(arg: Tuple[str, List[Getter]]) -> Lookup:
    return Lookup(arg[0], arg[1])


@dataclasses.dataclass(frozen=True)
class Call(Item):
    func: FuncDef
    args: Sequence[Item]

    async def eval(self, root: RootABC) -> TypeT:
        args = [await a.eval(root) for a in self.args]
        ret = await self.func.call(root, *args)  # type: ignore
        return cast(TypeT, ret)


def make_args(arg: Optional[Tuple[Item, List[Item]]]) -> List[Item]:
    if arg is None:
        return []
    first, tail = arg
    return [first] + tail[:]


def make_call(arg: Tuple[str, List[Item]]) -> Call:
    funcname, args = arg
    try:
        spec = FUNCTIONS[funcname]
    except KeyError:
        raise LookupError(f"Unknown function {funcname}")
    args_count = len(args)
    dummies = [None] * args_count
    spec.sig.bind(None, *dummies)
    return Call(spec, args)


@dataclasses.dataclass(frozen=True)
class Text(Item):
    arg: str

    async def eval(self, root: RootABC) -> str:
        return self.arg


def make_text(arg: Token) -> Text:
    return Text(tokval(arg))


DOT = skip(a(Token("DOT", ".")))
COMMA = skip(a(Token("COMMA", ",")))

OPEN_TMPL = skip(a(Token("LTMPL", "${{")))
CLOSE_TMPL = skip(a(Token("RTMPL", "}}")))

LPAR = skip(a(Token("LPAR", "(")))
RPAR = skip(a(Token("RPAR", ")")))

LSQB = skip(a(Token("LSQB", "[")))
RSQB = skip(a(Token("RSQB", "]")))

REAL = literal("REAL") | literal("EXP")

INT = literal("INT") | literal("HEX") | literal("OCT") | literal("BIN")

BOOL = literal("BOOL")

STR = literal("STR")

NONE = literal("NONE")

LITERAL = NONE | BOOL | REAL | INT | STR

NAME = some(lambda tok: tok.type == "NAME") >> tokval

ATOM = LITERAL  # | list-make | dict-maker

EXPR = forward_decl()

ATOM_EXPR = forward_decl()

LOOKUP_ATTR = DOT + NAME >> lookup_attr

LOOKUP_ITEM = LSQB + EXPR + RSQB >> lookup_item

LOOKUP = NAME + many(LOOKUP_ATTR | LOOKUP_ITEM) >> make_lookup

FUNC_ARGS = maybe(EXPR + many(COMMA + EXPR)) >> make_args


FUNC_CALL = (NAME + LPAR + FUNC_ARGS + RPAR) >> make_call


ATOM_EXPR.define(ATOM | FUNC_CALL | LOOKUP)


EXPR.define(ATOM_EXPR)


TMPL = OPEN_TMPL + EXPR + CLOSE_TMPL

TEXT = some(lambda tok: tok.type == "TEXT") >> make_text

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

    async def eval(self, root: RootABC) -> Optional[_T]:
        if self._ret is not None:
            return self._ret
        if self._parsed is not None:
            ret: List[str] = []
            for part in self._parsed:
                val = await part.eval(root)
                # TODO: add str() function, raise an explicit error if
                # an expresion evaluates non-str type
                # assert isinstance(val, str), repr(val)
                ret.append(str(val))
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

    async def eval(self, root: RootABC) -> _T:
        ret = await super().eval(root)
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


class IntExprMixin:
    @classmethod
    def convert(cls, arg: str) -> int:
        return int(literal_eval(arg))


class IntExpr(IntExprMixin, StrictExpr[int]):
    pass


class OptIntExpr(IntExprMixin, Expr[int]):
    pass


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
