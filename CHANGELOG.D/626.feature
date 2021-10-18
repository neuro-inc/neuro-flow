Added support of non-string types for action inputs. Now, one can specify action input in following way:

```
inputs:
  arg1:
    descr: Input with implicit string type
  arg2:
    descr: Input with explicit string type
    type: str
   arg2:
    descr: Input with explicit int type and corresponding default
    type: int
    default: 42
```

Supported types are `int`, `float`, `bool`, `str`. On action calls side, it's now possible to use
corresponding yaml types as arguments.
