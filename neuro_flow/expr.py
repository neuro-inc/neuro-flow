# expression parser/evaluator
# ${{ <expression> }}
import dataclasses

import abc
import asyncio
import collections
import datetime
import enum
import hashlib
import inspect
import json
import operator
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
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)
from typing_extensions import Final, Protocol, runtime_checkable
from yarl import URL

from .tokenizer import Pos, Token, tokenize
from .types import AlwaysT, LocalPath, RemotePath, TaskStatus
from .utils import run_subproc


_T = TypeVar("_T")


LiteralT = Union[None, bool, int, float, str]

TypeT = Union[LiteralT, "ContainerT", "MappingT", "SequenceT", LocalPath, AlwaysT]


@runtime_checkable
class ContainerT(Protocol):
    def __getattr__(self, attr: str) -> TypeT:
        ...


@runtime_checkable
class MappingT(Protocol):
    def __getitem__(self, key: LiteralT) -> TypeT:
        ...

    def __iter__(self) -> Iterator[LiteralT]:
        ...


@runtime_checkable
class SequenceT(Protocol):
    def __getitem__(self, idx: LiteralT) -> TypeT:
        ...

    def __iter__(self) -> Iterator[TypeT]:
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
    # Async version of list(), async is required for the sake of uniformness.
    if not isinstance(arg, Mapping):
        raise TypeError(f"keys() requires a mapping, got {arg!r}")
    return list(arg)  # type: ignore  # List[...] is implicitly converted to SequenceT


async def fmt(ctx: CallCtx, spec: str, *args: TypeT) -> str:
    # We need a trampoline since expression syntax doesn't support classes and named
    # argumens
    return spec.format(*args)


class JSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        elif isinstance(obj, enum.Enum):
            return obj.value
        elif isinstance(obj, RemotePath):
            return str(obj)
        elif isinstance(obj, LocalPath):
            return str(obj)
        elif isinstance(obj, collections.abc.Set):
            return sorted(obj)
        elif isinstance(obj, AlwaysT):
            return str(obj)
        elif isinstance(obj, URL):
            return str(obj)
        # Let the base class default method raise the TypeError
        return super().default(obj)


async def to_json(ctx: CallCtx, arg: TypeT) -> str:
    return json.dumps(arg, cls=JSONEncoder)


async def from_json(ctx: CallCtx, arg: str) -> TypeT:
    return cast(TypeT, json.loads(arg))


async def hash_files(ctx: CallCtx, *patterns: str) -> str:
    hasher = hashlib.new("sha256")
    flow = ctx.root.lookup("flow")
    # emulate attr lookup
    workspace: LocalPath = cast(
        LocalPath,
        await AttrGetter(ctx.start, ctx.end, name="workspace").eval(
            ctx.root, flow, start=ctx.start
        ),
    )
    for pattern in patterns:
        for fname in sorted(workspace.glob(pattern)):
            with fname.open("rb") as stream:
                data = stream.read(256 * 1024)
                if not data:
                    break
                hasher.update(data)
    return hasher.hexdigest()


async def upload(ctx: CallCtx, volume_ctx: ContainerT) -> ContainerT:
    from .context import VolumeCtx

    if not isinstance(volume_ctx, VolumeCtx):
        raise ValueError("upload() argument should be volume")
    await run_subproc(
        "neuro",
        "cp",
        "--recursive",
        "--update",
        "--no-target-directory",
        str(volume_ctx.full_local_path),
        str(volume_ctx.remote),
    )
    return volume_ctx


def _check_has_needs(ctx: CallCtx, *, func_name: str) -> None:
    try:
        ctx.root.lookup("needs")
    except LookupError:
        raise ValueError(f"{func_name}() is only available inside a task definition")


def _get_needs_statuses(root: RootABC) -> Dict[str, TaskStatus]:
    needs = root.lookup("needs")
    assert isinstance(needs, MappingT)
    result: Dict[str, TaskStatus] = {}
    for dependency in needs:
        dep_ctx = needs[dependency]
        result[dependency] = dep_ctx.result  # type: ignore
    return result


async def always(ctx: CallCtx, *args: str) -> AlwaysT:
    _check_has_needs(ctx, func_name="success")
    return AlwaysT()


async def success(ctx: CallCtx, *args: str) -> bool:
    # When called without arguments, checks that all dependency task
    # succeeded. If arguments are passed, they should be strings that
    # name some task from `needs:` field. Function will return true
    # if all of those tasks succeded.
    _check_has_needs(ctx, func_name="success")
    needs_statuses = _get_needs_statuses(ctx.root)
    if not args:
        return all(status == TaskStatus.SUCCEEDED for status in needs_statuses.values())
    else:
        if not all(isinstance(arg, str) for arg in args):
            raise ValueError("success() function only accept string arguments")
        try:
            return all(needs_statuses[need] == TaskStatus.SUCCEEDED for need in args)
        except KeyError as e:
            raise ValueError(
                "success() function got argument, that"
                f'is not a defined as dependency: "{e.args[0]}"'
            )


async def failure(ctx: CallCtx, *args: str) -> bool:
    # When called without arguments, checks if any of dependency task
    # failed. If arguments are passed, they should be strings that
    # name some task from `needs:` field. Function will return true
    # if any of those tasks failure.
    _check_has_needs(ctx, func_name="failure")
    needs_statuses = _get_needs_statuses(ctx.root)
    if not args:
        return any(status == TaskStatus.FAILED for status in needs_statuses.values())
    else:
        if not all(isinstance(arg, str) for arg in args):
            raise ValueError("failure() function only accept string arguments")
        try:
            return any(needs_statuses[need] == TaskStatus.FAILED for need in args)
        except KeyError as e:
            raise ValueError(
                "failure() function got argument, that"
                f'is not a defined as dependency: "{e.args[0]}"'
            )


FUNCTIONS = _build_signatures(
    len=alen,
    nothing=nothing,
    fmt=fmt,
    keys=akeys,
    to_json=to_json,
    from_json=from_json,
    success=success,
    failure=failure,
    hash_files=hash_files,
    always=always,
    upload=upload,
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
            call_ctx = CallCtx(self.start, self.end, root)
            tmp = await self.func.call(call_ctx, *args)  # type: ignore
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


@dataclasses.dataclass(frozen=True)
class BinOp(Item):
    op: Callable[[TypeT, TypeT], TypeT]
    left: Item
    right: Item

    async def eval(self, root: RootABC) -> TypeT:
        left_val = await self.left.eval(root)
        right_val = await self.right.eval(root)
        return self.op(left_val, right_val)  # type: ignore


def make_bin_op_expr(args: Tuple[Item, Token, Item]) -> BinOp:
    op_map = {
        "==": operator.eq,
        "!=": operator.ne,
        "or": operator.or_,
        "and": operator.and_,
        "<": operator.lt,
        "<=": operator.le,
        ">": operator.gt,
        ">=": operator.ge,
    }
    op_token = args[1]
    return BinOp(
        args[0].start,
        args[2].end,
        op=op_map[op_token.value],
        left=args[0],
        right=args[2],
    )


@dataclasses.dataclass(frozen=True)
class UnaryOp(Item):
    op: Callable[[TypeT], TypeT]
    operand: Item

    async def eval(self, root: RootABC) -> TypeT:
        operand_val = await self.operand.eval(root)
        return self.op(operand_val)  # type: ignore


def make_unary_op_expr(args: Tuple[Token, Item]) -> UnaryOp:
    op_map = {
        "not": operator.not_,
    }
    op_token = args[0]
    return UnaryOp(
        args[0].start,
        args[1].end,
        op=op_map[op_token.value],
        operand=args[1],
    )


def a(value: str) -> Parser:
    """Eq(a) -> Parser(a, a)

    Returns a parser that parses a token that is equal to the value value.
    """
    return some(lambda t: t.value == value).named(f'(a "{value}")')


DOT: Final = skip(a("."))
COMMA: Final = skip(a(","))

OPEN_TMPL: Final = skip(a("${{"))
CLOSE_TMPL: Final = skip(a("}}"))
OPEN_TMPL2: Final = skip(a("$[["))
CLOSE_TMPL2: Final = skip(a("]]"))

LPAR: Final = skip(a("("))
RPAR = skip(a(")"))

LSQB: Final = skip(a("["))
RSQB = skip(a("]"))

BIN_OP = a("==") | a("!=") | a("or") | a("and") | a("<") | a("<=") | a(">") | a(">=")
UNARY_OP = a("not")

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


ATOM_EXPR.define(ATOM | FUNC_CALL | LOOKUP | LPAR + EXPR + RPAR)

BIN_OP_EXPR: Final = ATOM_EXPR + BIN_OP + EXPR >> make_bin_op_expr

UNARY_OP_EXPR: Final = UNARY_OP + EXPR >> make_unary_op_expr

EXPR.define(BIN_OP_EXPR | UNARY_OP_EXPR | ATOM_EXPR)


TMPL: Final = (OPEN_TMPL + EXPR + CLOSE_TMPL) | (OPEN_TMPL2 + EXPR + CLOSE_TMPL2)

TEXT: Final = some(lambda tok: tok.type == "TEXT") >> make_text

PARSER: Final = oneplus(TMPL | TEXT) + skip(finished)


class Expr(Generic[_T]):
    allow_none = True
    allow_expr = True
    type: Type[_T]
    _ret: Union[None, _T]
    _pattern: Union[None, str, _T]
    _parsed: Optional[Sequence[Item]]

    @classmethod
    @abc.abstractmethod
    def convert(cls, arg: Union[str, _T]) -> _T:
        pass

    def _try_convert(self, arg: Union[str, _T], start: Pos, end: Pos) -> None:
        try:
            self._ret = self.convert(arg)
        except (TypeError, ValueError) as exc:
            raise EvalError(str(exc), start, end)

    def __init__(self, start: Pos, end: Pos, pattern: Union[None, str, _T]) -> None:
        self._pattern = pattern
        # precalculated value for constant string, allows raising errors earlier
        self._ret = None
        if pattern is not None:
            if isinstance(pattern, str):
                # parse later
                pass
            elif isinstance(pattern, self.type):
                # explicit non-string value is passed
                self._try_convert(pattern, start, end)
                return
            else:
                raise EvalError(f"str is expected, got {type(pattern)}", start, end)
            tokens = list(tokenize(pattern, start=start))
            if tokens:
                self._parsed = PARSER.parse(tokens)
            else:
                self._parsed = [Text(start, end, "")]
            assert self._parsed
            if len(self._parsed) == 1 and type(self._parsed[0]) == Text:
                self._try_convert(cast(Text, self._parsed[0]).arg, start, end)
            elif not self.allow_expr:
                raise EvalError(f"Expressions are not allowed in {pattern}", start, end)
        elif self.allow_none:
            self._parsed = None
        else:
            raise EvalError("None is not allowed", start, end)

    @property
    def pattern(self) -> Optional[str]:
        if self._pattern is None:
            return None
        return str(self._pattern)

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


class StrExprMixin:
    @classmethod
    def convert(cls, arg: str) -> str:
        return arg


class StrExpr(StrExprMixin, StrictExpr[str]):
    type = str


class OptStrExpr(StrExprMixin, Expr[str]):
    type = str


class SimpleStrExpr(StrExprMixin, StrictExpr[str]):
    allow_expr = False
    type = str


class SimpleOptStrExpr(StrExprMixin, Expr[str]):
    allow_expr = False
    type = str


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
    type = str


class OptIdExpr(IdExprMixin, Expr[str]):
    type = str


class SimpleIdExpr(IdExprMixin, StrictExpr[str]):
    allow_expr = False
    type = str


class SimpleOptIdExpr(IdExprMixin, Expr[str]):
    allow_expr = False
    type = str


class URIExprMixin:
    @classmethod
    def convert(cls, arg: Union[str, URL]) -> URL:
        return URL(arg)


class URIExpr(URIExprMixin, StrictExpr[URL]):
    type = URL


class OptURIExpr(URIExprMixin, Expr[URL]):
    type = URL


class BoolExprMixin:
    @classmethod
    def convert(cls, arg: Union[str, bool]) -> bool:
        if isinstance(arg, bool):
            return arg
        tmp = parse_literal(arg, "a boolean")
        return bool(tmp)


class BoolExpr(BoolExprMixin, StrictExpr[bool]):
    type = bool


class OptBoolExpr(BoolExprMixin, Expr[bool]):
    type = bool


class SimpleBoolExpr(BoolExprMixin, StrictExpr[bool]):
    allow_expr = False
    type = bool


class SimpleOptBoolExpr(BoolExprMixin, Expr[bool]):
    allow_expr = False
    type = bool


class EnableExprMixin:
    @classmethod
    def convert(cls, arg: Union[AlwaysT, str, bool]) -> Union[bool, AlwaysT]:
        if isinstance(arg, AlwaysT) or isinstance(arg, bool):
            return arg
        if arg == "always()":
            return AlwaysT()
        tmp = parse_literal(arg, "a boolean")
        return bool(tmp)


class EnableExpr(EnableExprMixin, StrictExpr[Union[bool, AlwaysT]]):
    type = bool


class OptEnableExpr(EnableExprMixin, Expr[Union[bool, AlwaysT]]):
    type = bool


class IntExprMixin:
    @classmethod
    def convert(cls, arg: Union[str, int]) -> int:
        if isinstance(arg, int):
            return arg
        tmp = parse_literal(arg, "an integer")
        return int(tmp)  # type: ignore[arg-type]


class IntExpr(IntExprMixin, StrictExpr[int]):
    type = int


class OptIntExpr(IntExprMixin, Expr[int]):
    type = int


class FloatExprMixin:
    @classmethod
    def convert(cls, arg: Union[str, float]) -> float:
        if isinstance(arg, float):
            return arg
        tmp = parse_literal(arg, "a float")
        return float(tmp)  # type: ignore[arg-type]


class FloatExpr(FloatExprMixin, StrictExpr[float]):
    type = float


class OptFloatExpr(FloatExprMixin, Expr[float]):
    type = float


class OptLifeSpanExpr(OptFloatExpr):
    RE = re.compile(r"^((?P<d>\d+)d)?((?P<h>\d+)h)?((?P<m>\d+)m)?((?P<s>\d+)s)?$")

    @classmethod
    def convert(cls, arg: Union[str, float]) -> float:
        try:
            return super(cls, OptLifeSpanExpr).convert(arg)
        except (ValueError, SyntaxError):
            assert isinstance(arg, str)
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
    def convert(cls, arg: Union[str, LocalPath]) -> LocalPath:
        return LocalPath(arg)


class LocalPathExpr(LocalPathMixin, StrictExpr[LocalPath]):
    type = LocalPath


class OptLocalPathExpr(LocalPathMixin, Expr[LocalPath]):
    type = LocalPath


class RemotePathMixin:
    @classmethod
    def convert(cls, arg: Union[str, RemotePath]) -> RemotePath:
        return RemotePath(arg)


class RemotePathExpr(RemotePathMixin, StrictExpr[RemotePath]):
    type = RemotePath


class OptRemotePathExpr(RemotePathMixin, Expr[RemotePath]):
    type = RemotePath


class OptBashExpr(OptStrExpr):
    @classmethod
    def convert(cls, arg: str) -> str:
        ret = " ".join(["bash", "-euo", "pipefail", "-c", shlex.quote(arg)])
        return ret


class OptPythonExpr(OptStrExpr):
    @classmethod
    def convert(cls, arg: str) -> str:
        ret = " ".join(["python3", "-uc", shlex.quote(arg)])
        return ret


class PortPairExpr(StrExpr):
    RE = re.compile(r"^\d+:\d+$")

    @classmethod
    def convert(cls, arg: str) -> str:
        match = cls.RE.match(arg)
        if match is None:
            raise ValueError(f"{arg!r} is not a LOCAL:REMOTE ports pair")
        return arg
