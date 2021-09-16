Mixins allow to define and reuse parts of jobs in live mode and tasks in batch mode. 

To define a mixin, use the top-level `mixins` section:

```yaml
...
mixins:
  credentials:
    volumes:
      - secret:some_key:/var/some_key
    env:
      KEY_LOCATION: /var/some_key
...
```

Mixins can define the same properties as "job" and "task" do, except for the "id" field in batch mode. To apply a mixin, use the `mixins` property:

```yaml
...
jobs:
  test_a:
    mixins: [ credentials ]
...
```

When applied, all fields defined in the mixin will be merged into the job definition. You can apply multiple mixins simultaneously. If some of the applied mixins share a property or/and this property is defined in a task, the following rules are applied:

* If the property is scalar (int/string/bool), the value from the job definition will be used. If the value is absent in the job definiton, it will be taken from the rightmost of the mixins that define this property.

```yaml
mixins:
  mix1:
    image: example_mix1
  mix2:
    image: example_mix2
jobs:
  job1:
    mixins: [mix1, mix2]
    image: example
  job2:
    mixins: [mix1, mix2]
```

In this case, `job1` will use the `example` image and `job2` will use the `example_mix2` image.

* If the property is a list, than all lists will be concatenated.
* If the property is a dictionary, the rule for scalar values will be applied to each value from the dictionary.

Mixins can inherit from each other:

```yaml
mixins:
  mix1:
    env:
      TEST: 1
  mix2:
    mixins: [ mix1 ]
    image: example
``` ([#498](https://github.com/neuro-inc/neuro-flow/issues/498))
```