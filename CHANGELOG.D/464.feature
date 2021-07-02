Added modules feature: a module is simillar to action but has following differneces:
- only local files support (`ws:` scheme), github located modules are forbidden.
- the module content has access to workflow global defaults. The default env/volumes/preset
is inherited, and expressions can access top level contexts such as `flow`.

Calling a module is similar to calling an action, except for use of `module` property
instead of `action` property:

Live module call:
```
jobs:
  test:
    module: ws:live-module
    args:
      arg1: val 1
```

Batch module call:
```
tasks:
  - id: test
    module: ws:batch-module
    args:
      arg1: val 1
```
