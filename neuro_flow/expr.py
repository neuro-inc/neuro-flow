# expression parser/evaluator
# ${{ <expression> }}

import dataclasses

import abc
import datetime
import inspect
import json
import re
import shlex
from ast import literal_eval
from collections.abc import Sized
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
from typing_extensions import Protocol, runtime_checkable
from yarl import URL


_T = TypeVar("_T")

Pos = Tuple[int, int]

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


class EvalErrorMixin:
    def __init__(self, msg: str, start: Pos, end: Pos) -> None:
        super().__init__(msg)  # type: ignore  # call exception class constructor
        self.start = start
        self.end = end


class EvalTypeError(EvalErrorMixin, TypeError):
    pass


class EvalValueError(EvalErrorMixin, ValueError):
    pass


class EvalLookupError(EvalErrorMixin, LookupError):
    pass


class Tokenizer:

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
        ("NAME", re.compile(r"[A-Za-z][A-Za-z_0-9]*")),
        ("DOT", re.compile(r"\.")),
        ("COMMA", re.compile(r",")),
        ("LPAR", re.compile(r"\(")),
        ("RPAR", re.compile(r"\)")),
        ("LSQB", re.compile(r"\[")),
        ("RSQB", re.compile(r"\]")),
    ]

    def make_token(self, typ: str, value: str, line: int, pos: int) -> Token:
        nls = value.count("\n")
        n_line = line + nls
        if nls == 0:
            n_pos = pos + len(value)
        else:
            n_pos = len(value) - value.rfind("\n") - 1
        return Token(typ, value, (line, pos), (n_line, n_pos))

    def match_specs(self, s: str, i: int, start: Pos, position: Pos) -> Token:
        line, pos = position
        for typ, regexp in self.TOKENS:
            m = regexp.match(s, i)
            if m is not None:
                return self.make_token(typ, m.group(), line, pos)
        else:
            errline = s.splitlines()[line - start[0]]
            raise LexerError((line + 1, pos + 1), " " * start[1] + errline)

    def match_text(self, s: str, i: int, start: Pos, position: Pos) -> Token:
        ltmpl = s.find("${{", i)
        if ltmpl == i:
            return None
        if ltmpl == -1:
            # LTMPL not found, use the whole string
            substr = s[i:]
        else:
            substr = s[i:ltmpl]
        line, pos = position
        err_pos = substr.find("}}")
        if err_pos != -1:
            t = self.make_token("TEXT", substr[:err_pos], line, pos)
            line, pos = t.end
            errline = s.splitlines()[line - start[0]]
            raise LexerError((line + 1, pos + 1), " " * start[1] + errline)
        return self.make_token("TEXT", substr, line, pos)

    def __call__(self, s: str, *, start: Pos = (0, 0)) -> Iterator[Token]:
        in_expr = False
        length = len(s)
        line, pos = start
        i = 0
        while i < length:
            if in_expr:
                t = self.match_specs(s, i, start, (line, pos))
                if t.type == "RTMPL":
                    in_expr = False
            else:
                t = self.match_text(s, i, start, (line, pos))
                if not t:
                    in_expr = True
                    t = self.match_specs(s, i, start, (line, pos))
            if t.type != "SPACE":
                yield t
            line, pos = t.end
            i += len(t.value)


tokenize = Tokenizer()


@dataclasses.dataclass(frozen=True)
class FuncDef:
    name: str
    sig: inspect.Signature
    call: Callable[..., Awaitable[TypeT]]


@dataclasses.dataclass
class CallCtx:
    start: Pos
    end: Pos
    root: RootABC


def _build_signatures(**kwargs: Callable[..., Awaitable[TypeT]]) -> Dict[str, FuncDef]:
    return {k: FuncDef(k, inspect.signature(v), v) for k, v in kwargs.items()}


async def nothing(ctx: CallCtx) -> None:
    # A test function that accepts none args.
    # Later we can replace it with something really more usefuld, e.g. succeded()
    return None


async def alen(ctx: CallCtx, arg: TypeT) -> int:
    # Async version of len(), async is required for the sake of uniformness.
    if not isinstance(arg, Sized):
        raise TypeError(f"len() requires a str, sequence or mapping, got {arg!r}")
    return len(arg)


async def akeys(ctx: CallCtx, arg: TypeT) -> TypeT:
    # Async version of len(), async is required for the sake of uniformness.
    if not isinstance(arg, Mapping):
        raise TypeError(f"keys() requires a mapping, got {arg!r}")
    return list(arg)  # type: ignore  # List[...] is implicitly converted to SequenceT


async def fmt(ctx: CallCtx, spec: str, *args: TypeT) -> str:
    # We need a trampoline since expression syntax doesn't support classes and named
    # argumens
    return spec.format(*args)


async def to_json(ctx: CallCtx, arg: TypeT) -> str:
    return json.dumps(arg)


async def from_json(ctx: CallCtx, arg: str) -> TypeT:
    return cast(TypeT, json.loads(arg))


FUNCTIONS = _build_signatures(
    len=alen, nothing=nothing, fmt=fmt, keys=akeys, to_json=to_json, from_json=from_json
)


@dataclasses.dataclass(frozen=True)
class Entity(abc.ABC):
    start: Pos
    end: Pos


class Item(Entity):
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
        return Literal(tok.start, tok.end, literal_eval(tok.value))

    return some(lambda tok: tok.type == toktype) >> f


class Getter(Entity):
    # Aux class for Lookup item

    @abc.abstractmethod
    async def eval(self, root: RootABC, obj: TypeT, start: Pos) -> TypeT:
        pass


@dataclasses.dataclass(frozen=True)
class AttrGetter(Getter):
    name: str

    async def eval(self, root: RootABC, obj: TypeT, start: Pos) -> TypeT:
        if dataclasses.is_dataclass(obj):
            name = self.name
            try:
                return cast(TypeT, getattr(obj, name))
            except AttributeError:
                raise EvalLookupError(f"No attribute {self.name}", start, self.end)
        elif isinstance(obj, MappingT):
            try:
                return obj[self.name]
            except KeyError:
                raise EvalLookupError(f"No attribute {self.name}", start, self.end)
        else:
            raise EvalTypeError(
                f"Is not an object with attributes accessible by a dot.",
                start,
                self.end,
            )


def lookup_attr(name: Token) -> Any:
    # Just in case, NAME token cannot start with _.
    assert not name.value.startswith("_")
    return AttrGetter(name.start, name.end, name.value)


@dataclasses.dataclass(frozen=True)
class ItemGetter(Getter):
    key: Item

    async def eval(self, root: RootABC, obj: TypeT, start: Pos) -> TypeT:
        assert isinstance(obj, (SequenceT, MappingT))
        key = cast(LiteralT, await self.key.eval(root))
        try:
            return obj[key]
        except LookupError:
            raise EvalLookupError(f"No item {self.key}", start, self.end)


def lookup_item(key: Item) -> Any:
    return ItemGetter(key.start, key.end, key)


@dataclasses.dataclass(frozen=True)
class Lookup(Item):
    root: str
    trailer: Sequence[Getter]

    async def eval(self, root: RootABC) -> TypeT:
        ret = root.lookup(self.root)
        start = self.start
        for op in self.trailer:
            ret = await op.eval(root, ret, start)
        return ret


def make_lookup(arg: Tuple[Token, List[Getter]]) -> Lookup:
    name, trailer = arg
    end = trailer[-1].end if trailer else name.end
    return Lookup(name.start, end, name.value, trailer)


def make_args(arg: Optional[Tuple[Item, List[Item]]]) -> List[Item]:
    if arg is None:
        return []
    first, tail = arg
    return [first] + tail[:]


@dataclasses.dataclass(frozen=True)
class Call(Item):
    func: FuncDef
    args: Sequence[Item]
    trailer: Sequence[Getter]

    async def eval(self, root: RootABC) -> TypeT:
        args = [await a.eval(root) for a in self.args]
        tmp = await self.func.call(root, *args)  # type: ignore
        ret = cast(TypeT, tmp)
        start = self.start
        for op in self.trailer:
            ret = await op.eval(root, ret, start)
        return ret


def make_call(arg: Tuple[Token, List[Item], Sequence[Getter]]) -> Call:
    funcname, args, trailer = arg
    try:
        spec = FUNCTIONS[funcname.value]
    except KeyError:
        raise LookupError(f"Unknown function {funcname.value}")
    end = funcname.end
    args_count = len(args)
    if args_count > 0:
        end = args[-1].end
    dummies = [None] * args_count
    spec.sig.bind(None, *dummies)
    if trailer:
        end = trailer[-1].end
    return Call(funcname.start, end, spec, args, trailer)


@dataclasses.dataclass(frozen=True)
class Text(Item):
    arg: str

    async def eval(self, root: RootABC) -> str:
        return self.arg


def make_text(arg: Token) -> Text:
    return Text(arg.start, arg.end, arg.value)


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

NAME = some(lambda tok: tok.type == "NAME")

ATOM = LITERAL  # | list-make | dict-maker

EXPR = forward_decl()

ATOM_EXPR = forward_decl()

LOOKUP_ATTR = DOT + NAME >> lookup_attr

LOOKUP_ITEM = LSQB + EXPR + RSQB >> lookup_item

TRAILER = many(LOOKUP_ATTR | LOOKUP_ITEM)

LOOKUP = NAME + TRAILER >> make_lookup

FUNC_ARGS = maybe(EXPR + many(COMMA + EXPR)) >> make_args

FUNC_CALL = (NAME + LPAR + FUNC_ARGS + RPAR + TRAILER) >> make_call


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

    def __init__(self, pattern: Optional[str], *, start: Pos = (0, 0)) -> None:
        self._pattern = pattern
        # precalculated value for constant string, allows raising errors earlier
        self._ret: Optional[_T] = None
        if pattern is not None:
            if not isinstance(pattern, str):
                raise TypeError(f"str is expected, got {type(pattern)}")
            tokens = list(tokenize(pattern, start=start))
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
        return f"{self.__class__.__qualname__}({self._pattern!r})"

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


class OptLifeSpanExpr(OptFloatExpr):
    RE = re.compile(r"^((?P<d>\d+)d)?((?P<h>\d+)h)?((?P<m>\d+)m)?((?P<s>\d+)s)?$")

    @classmethod
    def convert(cls, arg: str) -> float:
        try:
            return float(literal_eval(arg))
        except (ValueError, SyntaxError):
            match = cls.RE.match(arg)
            if match is None:
                raise ValueError(f"{arg} is not a life span")
            td = datetime.timedelta(
                days=int(match.group("d") or 0),
                hours=int(match.group("h") or 0),
                minutes=int(match.group("m") or 0),
                seconds=int(match.group("s") or 0),
            )
            return td.total_seconds()


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


class OptBashExpr(OptStrExpr):
    @classmethod
    def convert(cls, arg: str) -> str:
        ret = " ".join(["bash", "-euxo", "pipefail", "-c", shlex.quote(arg)])
        return ret


class OptPythonExpr(OptStrExpr):
    @classmethod
    def convert(cls, arg: str) -> str:
        ret = " ".join(["python3", "-c", shlex.quote(arg)])
        return ret


class PortPairExpr(StrExpr):
    RE = re.compile(r"^\d+:\d+$")

    @classmethod
    def convert(cls, arg: str) -> str:
        match = cls.RE.match(arg)
        if match is None:
            raise ValueError(f"{arg} is not a LOCAL:REMOTE ports pairn")
        return arg
