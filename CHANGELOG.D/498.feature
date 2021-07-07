Add support of mixins in live and batch mode.

Mixins allow to define and reuse some common parts of jobs in live mode and tasks in batch mode.
To define a mixin, use top level `mixins` sections:
```
...
mixins:
  credentials:
    volumes:
      - secret:some_key:/var/some_key
    env:
      KEY_LOCATION: /var/some_key
...
```

Mixins can define the same properties as "job" and "task" do, except for "id" field in batch mode.
To apply a mixin, use `inherits` property:

```
...
jobs:
  test_a:
    inherits: [ credentials ]
...
```

When applied, all fields defined in mixin will be merged into job definition.
You can apply multiple mixins simultaneously. If some of applied mixins share the same property,
or/and it is defined in task, the following rules are applied:
- If property is scalar (int/string/bool), then job will use value defined in job definition. If it is absent,
the value from the rightmost of the mixins that define this property will be used:
```
mixins:
  mix1:
    image: example_mix1
  mix2:
    image: example_mix2
jobs:
  job1:
    inherits: [mix1, mix2]
    image: example
  job2:
    inherits: [mix1, mix2]
```
The `job1` will use `example` image, and `job2` will use `example_mix2` image.
- If property is list, that all lists will be concatenated.
- If property is dict, that rule for scalars will be applied for dict values separately.

Mixins can inherit from each other:
```
mixins:
  mix1:
    env:
      TEST: 1
  mix2:
    inherits: [ mix1 ]
    image: example
```
