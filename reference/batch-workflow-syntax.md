# Batch workflow syntax

## _Batch_ workflow

The batch workflow is located at `.neuro/<batch-name>.yml` file under the project root;`.neuro/<batch-name>.yaml` is also supported if you prefer a longer suffix for some reason. The config filename should be a valid identifier if the [`id`](batch-workflow-syntax.md#id) attribute is not specified. The following YAML attributes are supported:

## `kind`

**Required** The workflow _kind_, _must be_ `batch` _for batch_ workflows.

## `id`

Identifier of the workflow. By default, the `id` is the filename of the workflow config without extension with hyphens \(`-`\) replaced with underscores \(`_`\).

## `title`

Workflow title.

## `defaults`

A map of default settings that will be applied to all tasks in the workflow. You can override these global default settings for a particular task.

### `defaults.fail_fast`

When set to `true`, the system cancels all in-progress tasks if some task fails. It can be overridden by [`tasks.strategy.fail_fast`](batch-workflow-syntax.md#tasks-strategy-fail_fast). Default: `true`

**Example:**

```yaml
defaults:
  fail_fast: false
```

### `defaults.max_parallel`

The maximum number of tasks that can run simultaneously during flow execution. By default, there is no limit.

**Example:**

```yaml
defaults:
  max_parallel: 4
```

### `defaults.cache`

A mapping that defines how caching of task outputs works. It can be overridden by [`tasks.cache`](batch-workflow-syntax.md#tasks-cache)\`\`

### `defaults.cache.strategy`

The default strategy to use for caching. Available options are:

* `"none"` Do not use caching at all.
* `"default"` The basic caching algorithm, that reuses cached outputs in case task definition and all [expression contexts](expression-syntax.md#contexts) available in task expressions are the same.

Default: `"default"`

**Example:**

```yaml
cache:
    strategy: "default"
```

### `defaults.cache.life_span`

The default cache invalidation duration. The attribute accepts either a `float` number of seconds or a string in`1d6h15m45s` \(1 day 6 hours, 15 minutes, 45 seconds\). Default: `14d` \(two weeks\)

{% hint style="info" %}
If you decrease this value and re-run flow, `neuro-flow` will ignore cache entries that were added more than the new value of`cache.life_span` seconds ago.  
{% endhint %}

**Example:**

```yaml
cache:
  life_span: 31d # Cache is valid for one month 
```

## `params`

Params is a mapping of key-value pairs that have a default value and could be overridden from a command line by using `neuro-flow bake <batch-id> --param NAME1 val1 --param NAME2 val2`

### `params.<param-name>.default`

The default value to use when param is not overridden from a command line.

**Example:**

```yaml
params:
  my-param: 
    default: default_value 
```

{% hint style="info" %}
In case you only want to specify the default value without description, you can use the following short-cut syntax:

```yaml
params:
  my_param: default_value
```
{% endhint %}

### `params.<param-name>.descr`

The human-readable description of the param. 

**Example:**

```yaml
params:
  my-param: 
    descr: This is param description 
```

## `images`

A mapping of image definitions used by this workflow.

Unlike _live_ flow images, _batch_ flow images cannot be build using `neuro-flow build <image-id>`. 

{% hint style="info" %}
The `images` section is not required, a task can specify the image name as a plain string without referring to `${{ images.my_image.ref }}` context.

The section exists for convenience: there is no need to repeat yourself if you can just point the image ref everywhere in the YAML.
{% endhint %}

{% hint style="danger" %}
The following fields are disabled in _batch_ flow and will cause an error:

* **`images.<image-id>.context`**
* **`images.<image-id>.dockerfile`**
* **`images.<image-id>.build_args`**
* **`images.<image-id>.env`**
* **`images.<image-id>.volumes`**
{% endhint %}

### `images.<image-id>`

The key `image-id` is a string and its value is a map of the tasks configuration data. You must replace `<image-id>` with a string that is unique to the `images` object. The `<image-id>` must start with a letter and contain only alphanumeric characters or `_`. Dash `-` is not allowed.

### `images.<image-id>.ref`

**Required** Image _reference_ that can be used in `tasks.image` expression.

You can use the image definition to _address_ images hosted ether on Neu.ro registry or [_Docker Hub_](https://hub.docker.com/search?q=&type=image). 

**Example:**

```yaml
images:
  my_image:
    ref: image:my_image:latest # Neu.ro registry hosted iamge 
  python:
    ref: python:3.9.0 # Docker Hub hosted image 
```

## `volumes`

A mapping of volume definitions available in this workflow. A volume defines a link between the Neu.ro storage folder and a remote folder that can be mounted to a task.

Unlike _live_ flow volumes,  _batch_ flow volumes **cannot** be synchronized by `neuro-flow upload` and `neuro-flow download` commands.  They can only be mounted to a task by using `task.volumes` attribute.

{% hint style="danger" %}
The following fields are disabled in _batch_ flow and will cause an error:

* **`volumes.<volume-id>.local`**
{% endhint %}

### `volumes.<volume-id>`

The key `volume-id` is a string and its value is a map of the volume's configuration data. You must replace `<volume-id>` with a string that is unique to the `volumes` object. The `<volume-id>` must start with a letter and contain only alphanumeric characters or `_`. Dash `-` is not allowed.

### `volumes.<volume-id>.remote`

**Required** The volume URI on the Neu.ro Storage.

**Example:**

```yaml
volumes:
  folder:
    remote: storage:path/to/folder
```

### `volumes.<volume-id>.mount`

**Required** The mount path inside a task.

**Example:**

```yaml
volumes:
  folder:
    mount: /mnt/folder
```

### `volumes.<volume-id>.read_only`

The volume is mounted as _read-only_ by default if the attribute is set, _read-write_ mode is used otherwise.

**Example:**

```yaml
volumes:
  folder:
    read_only: true
```

## `tasks`

List of tasks that this batch workflow contains. Unlike jobs in the live workflow, all tasks are executed with one command in the order that specified by [`tasks.needs`](batch-workflow-syntax.md#tasks-needs) . To start execution, run `neuro-flow bake <batch-id>`.

**Example:**

```yaml
tasks:
  - id: task_1
  - id: task_2 
  - id: task_3
```

### `tasks.id`

 A unique identifier for the task. It is used to reference the task in [`tasks.needs`](batch-workflow-syntax.md#tasks-needs). The value must start with a letter and contain only alphanumeric characters or underscore \(`_`\). Dash \(`-`\) is not allowed.   
  


{% hint style="info" %}
It is impossible to refer to tasks without an id inside the workflow file, but you can refer to them as `task-<num>`in command line output. The `<num>` here is an index in the [`tasks`](batch-workflow-syntax.md#tasks) list.
{% endhint %}

### `tasks.needs`

The array of strings identifying all tasks that must complete successfully before this task will run. If a task fails, all tasks that need it are skipped unless the task uses a [`tasks.enable`](batch-workflow-syntax.md#tasks-enable) statement that causes the task to ignore dependency failure.  
By default, `tasks.needs` is set to the previous task in the [`tasks`](batch-workflow-syntax.md#tasks) list. In case the previous task has[`matrix`](batch-workflow-syntax.md#tasks-strategy-matrix) set, the task will only run after all matrix tasks are completed.  
This property also specifies what entries are available in the needs &lt;link here&gt; context.

**Example 1:**

```yaml
tasks:
  - id: task_1  
  - id: task_2
    needs: [tasks_1] 
  - id: task_3
    needs: [tasks_2]
```

In this case, tasks will be executed in the following order:

1. task\_1
2. task\_2
3. task\_3

The order is the same as with the default behavior \(without `needs`\).  
  
**Example 2:**

```yaml
tasks:
  - id: task_1  
  - id: task_2
    needs: [] 
  - id: task_3
    needs: [task_1, tasks_2]
```

In this case, tasks will be executed in the following order:

1. task\_1 and task\_2 \(simultaneously\)
2. task\_3

{% hint style="info" %}
You can use `neuro-flow inspect --view BAKE_ID` to view the graph of running batch tasks rendered to pdf.
{% endhint %}

### `tasks.enable`

The flag to conditionally prevent a task from running unless a condition is met. To learn how to write conditions refer to [expression syntax](expression-syntax.md). Default: `${{ success() }}`

**Example:**

```yaml
tasks:
  - enable: ${{ always() }} # Run this task in any case 
  - enable: ${{ flow.id == "some-value" }} # Simple condition
```

### `tasks.strategy`

A mapping that defines a matrix and some auxiliary attributes to run multiple instances of the same task. 

### `tasks.strategy.matrix`

The matrix attribute defines a set of run configurations to run this task. Each key in this mapping sets some variable that will be available in the `matrix` context in expressions in this task. Each value should be an array and neuro-flow `neuro-flow` will start task variants with all possible combinations items of these arrays. The matrix can generate at most 256 different tasks.

**Example 1:**

```yaml
id: example_${{ matrix.param }}
strategy:
  matrix:
    param: [a, b]
```

In this example task with ids `example_a` and `example_b` will be generated

**Example 2:**

```yaml
id: ${{ matrix.param1 }}_${{ matrix.param2 }}
strategy:
  matrix:
    param1: [a, b]
    param2: [x, y]
```

In this example task with ids `a_x`, `a_y`,`b_x`, `b_y` will be generated.

{% hint style="info" %}
Auto-generated id with for matrix tasks will suffix in form of `-<param-1>-<param-2>`
{% endhint %}

### `tasks.strategy.matrix.exclude`

Exclude is a list of combinations to remove from the matrix. These entries can be partial, in this case all matching combinations are excluded.

**Example:**

```yaml
id: ${{ matrix.param1 }}_${{ matrix.param2 }}_${{ matrix.param3 }}
strategy:
  matrix:
    param1: [a, b]
    param2: [x, y]
    param3: [1, 2]
    exclude:
      - param1: a
        param2: x
        param3: 1
      - param1: b
        param2: y
```

In this example task with ids `a_x_2`, `a_y_1`,`a_y_2`, `b_x_1` , `b_x_2` will be generated.

### `tasks.strategy.matrix.include`

Include is a list of combinations to add to the matrix. These entries cannot be partial. In case [`exclude`](batch-workflow-syntax.md#tasks-strategy-matrix-exclude) is also present, `include` will be applied after it.

**Example:**

```yaml
id: ${{ matrix.param1 }}_${{ matrix.param2 }}_${{ matrix.param3 }}
strategy:
  matrix:
    param1: [a, b]
    param2: [x, y]
    include:
      - param1: a
        param2: z
```

In this example task with ids `a_x`, `a_y`,`b_x`, `b_y` , `a_z` will be generated.

### `tasks.strategy.fail_fast`

When set to `true`, the system cancels all in-progress tasks if this task or any of its matrix tasks fails. Default: `true`

### `tasks.strategy.max_parallel`

The maximum number of matrix tasks that can run simultaneously. By default, there is no limit.

### `tasks.cache`

A mapping that defines how caching of this task outputs works. 

### `tasks.cache.strategy`

The strategy to use for caching of this task. Available options are:

* `"none"` Do not use caching at all.
* `"inherit"` Use the flow default value from [`defaults.cache.stategy`](batch-workflow-syntax.md#defaults-cache-strategy)\`\`
* `"default"` The basic caching algorithm, that reuses cached outputs in case task definition and all [expression contexts](expression-syntax.md#contexts) available in task expressions are the same.

Default: `"inherit"`

**Example:**

```yaml
cache:
    strategy: "none"
```

### `defaults.cache.life_span`

The cache invalidation duration. The attribute accepts either a `float` number of seconds or a string in`1d6h15m45s` \(1 day 6 hours, 15 minutes, 45 seconds\). Defaults to [`defaults.cache.life_span`](batch-workflow-syntax.md#defaults-cache-life_span) if not specified.

{% hint style="info" %}
If you decrease this value and re-run flow, `neuro-flow` will ignore cache entries that were added more than the new value of`cache.life_span` seconds ago.  
{% endhint %}

**Example:**

```yaml
cache:
  life_span: 31d # Cache is valid for one month
```

####  ExecUnit options are the same as for jobs

