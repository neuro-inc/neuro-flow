# expression parser/evaluator
# ${{ <expression> }}

import dataclasses

import abc
import asyncio
import datetime
import inspect
import json
import re
import shlex
from ast import literal_eval
from collections.abc import Sized
from funcparserlib.parser import (
    Parser,
    finished,
    forward_decl,
    many,
    maybe,
    oneplus,
    skip,
    some,
)
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Generic,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    cast,
)
from typing_extensions import Final, Protocol, runtime_checkable
from yarl import URL

from .tokenizer import Pos, Token, tokenize
from .types import LocalPath, RemotePath


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


class EvalError(Exception):
    def __init__(self, msg: str, start: Pos, end: Pos) -> None:
        super().__init__(msg)
        self.start = start
        self.end = end

    def __str__(self) -> str:
        line = self.start.line
        col = self.start.col
        return str(self.args[0]) + f"\n  in line {line}, column {col}"


def parse_literal(arg: str, err_msg: str) -> LiteralT:
    try:
        return cast(LiteralT, literal_eval(arg))
    except (ValueError, SyntaxError):
        raise ValueError(f"'{arg}' is not " + err_msg)


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
                raise EvalError(f"No attribute {self.name}", start, self.end)
        elif isinstance(obj, MappingT):
            try:
                return obj[self.name]
            except KeyError:
                raise EvalError(f"No attribute {self.name}", start, self.end)
        else:
            raise EvalError(
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
            raise EvalError(f"No item {self.key}", start, self.end)


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
        try:
            tmp = await self.func.call(root, *args)  # type: ignore
        except asyncio.CancelledError:
            raise
        except EvalError:
            raise
        except Exception as exc:
            raise EvalError(str(exc), self.start, self.end)
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


def a(value: str) -> Parser:
    """Eq(a) -> Parser(a, a)

    Returns a parser that parses a token that is equal to the value value.
    """
    return some(lambda t: t.value == value).named(f'(a "{value}")')


DOT: Final = skip(a("."))
COMMA: Final = skip(a(","))

OPEN_TMPL: Final = skip(a("${{"))
CLOSE_TMPL: Final = skip(a("}}"))

LPAR: Final = skip(a("("))
RPAR = skip(a(")"))

LSQB: Final = skip(a("["))
RSQB = skip(a("]"))

REAL: Final = literal("REAL") | literal("EXP")

INT: Final = literal("INT") | literal("HEX") | literal("OCT") | literal("BIN")

BOOL: Final = literal("BOOL")

STR: Final = literal("STR")

NONE: Final = literal("NONE")

LITERAL: Final = NONE | BOOL | REAL | INT | STR

NAME: Final = some(lambda tok: tok.type == "NAME")

ATOM: Final = LITERAL  # | list-make | dict-maker

EXPR: Final = forward_decl()

ATOM_EXPR: Final = forward_decl()

LOOKUP_ATTR: Final = DOT + NAME >> lookup_attr

LOOKUP_ITEM: Final = LSQB + EXPR + RSQB >> lookup_item

TRAILER: Final = many(LOOKUP_ATTR | LOOKUP_ITEM)

LOOKUP: Final = NAME + TRAILER >> make_lookup

FUNC_ARGS: Final = maybe(EXPR + many(COMMA + EXPR)) >> make_args

FUNC_CALL: Final = (NAME + LPAR + FUNC_ARGS + RPAR + TRAILER) >> make_call


ATOM_EXPR.define(ATOM | FUNC_CALL | LOOKUP)


EXPR.define(ATOM_EXPR)


TMPL: Final = OPEN_TMPL + EXPR + CLOSE_TMPL

TEXT: Final = some(lambda tok: tok.type == "TEXT") >> make_text

PARSER: Final = oneplus(TMPL | TEXT) + skip(finished)


class Expr(Generic[_T]):
    allow_none = True

    @classmethod
    def convert(cls, arg: str) -> _T:
        # implementation for StrExpr and OptStrExpr
        return cast(_T, arg)

    def __init__(self, start: Pos, end: Pos, pattern: Optional[str]) -> None:
        self._pattern = pattern
        # precalculated value for constant string, allows raising errors earlier
        self._ret: Optional[_T] = None
        if pattern is not None:
            if not isinstance(pattern, str):
                raise EvalError(f"str is expected, got {type(pattern)}", start, end)
            tokens = list(tokenize(pattern, start=start))
            self._parsed: Optional[Sequence[Item]] = PARSER.parse(tokens)
            assert self._parsed is not None
            if len(self._parsed) == 1 and type(self._parsed[0]) == Text:
                try:
                    self._ret = self.convert(cast(Text, self._parsed[0]).arg)
                except (TypeError, ValueError) as exc:
                    raise EvalError(str(exc), start, end)
        elif self.allow_none:
            self._parsed = None
        else:
            raise EvalError("None is not allowed", start, end)

    @property
    def pattern(self) -> Optional[str]:
        return self._pattern

    async def eval(self, root: RootABC) -> Optional[_T]:
        if self._ret is not None:
            return self._ret
        if self._parsed is not None:
            ret: List[str] = []
            for part in self._parsed:
                try:
                    val = await part.eval(root)
                except asyncio.CancelledError:
                    raise
                except EvalError:
                    raise
                except Exception as exc:
                    raise EvalError(str(exc), part.start, part.end)
                # TODO: add str() function, raise an explicit error if
                # an expresion evaluates non-str type
                # assert isinstance(val, str), repr(val)
                ret.append(str(val))
            try:
                return self.convert("".join(ret))
            except asyncio.CancelledError:
                raise
            except EvalError:
                raise
            except Exception as exc:
                raise EvalError(str(exc), self._parsed[0].start, self._parsed[-1].end)
        else:
            # __init__() makes sure that the pattern is not None if
            # self.allow_none is False, the check is present here
            # for better readability.
            assert self.allow_none
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


class StrictExpr(Expr[_T]):
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


class IdExprMixin:
    @classmethod
    def convert(cls, arg: str) -> str:
        if not arg.isidentifier():
            raise ValueError(f"{arg!r} is not identifier")
        if arg == arg.upper():
            raise ValueError(
                f"{arg!r} is invalid identifier, "
                "uppercase names are reserved for internal usage"
            )
        return arg


class IdExpr(IdExprMixin, StrictExpr[str]):
    pass


class OptIdExpr(IdExprMixin, Expr[str]):
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
        tmp = parse_literal(arg, "a boolean")
        return bool(tmp)


class BoolExpr(BoolExprMixin, StrictExpr[bool]):
    pass


class OptBoolExpr(BoolExprMixin, Expr[bool]):
    pass


class IntExprMixin:
    @classmethod
    def convert(cls, arg: str) -> int:
        tmp = parse_literal(arg, "an integer")
        return int(tmp)  # type: ignore[arg-type]


class IntExpr(IntExprMixin, StrictExpr[int]):
    pass


class OptIntExpr(IntExprMixin, Expr[int]):
    pass


class FloatExprMixin:
    @classmethod
    def convert(cls, arg: str) -> float:
        tmp = parse_literal(arg, "a float")
        return float(tmp)  # type: ignore[arg-type]


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
                raise ValueError(f"{arg!r} is not a life span")
            td = datetime.timedelta(
                days=int(match.group("d") or 0),
                hours=int(match.group("h") or 0),
                minutes=int(match.group("m") or 0),
                seconds=int(match.group("s") or 0),
            )
            return td.total_seconds()


class LocalPathMixin:
    @classmethod
    def convert(cls, arg: str) -> LocalPath:
        return LocalPath(arg)


class LocalPathExpr(LocalPathMixin, StrictExpr[LocalPath]):
    pass


class OptLocalPathExpr(LocalPathMixin, Expr[LocalPath]):
    pass


class RemotePathMixin:
    @classmethod
    def convert(cls, arg: str) -> RemotePath:
        return RemotePath(arg)


class RemotePathExpr(RemotePathMixin, StrictExpr[RemotePath]):
    pass


class OptRemotePathExpr(RemotePathMixin, Expr[RemotePath]):
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
            raise ValueError(f"{arg!r} is not a LOCAL:REMOTE ports pair")
        return arg
