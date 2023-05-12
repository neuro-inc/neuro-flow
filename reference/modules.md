# Modules

Modules are simillar to [actions](broken-reference), but have the following differences:

* Only local files (`ws:` scheme) are supported. Modules located on GitHub are forbidden.
* Module content has access to global workflow defaults. The default `env/volumes/preset` is inherited and expressions can access top-level contexts such as `flow`.

Calling a module is similar to calling an action, except the `module` property is used instead of the `action` property.

## Live module call

```yaml
jobs:
  test:
    module: ws:live-module
    args:
      arg1: val 1
```

## Batch module call

```yaml
tasks:
  - id: test
    module: ws:batch-module
    args:
      arg1: val 1
```
