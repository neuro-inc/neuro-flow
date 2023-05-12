# Batch workflow syntax

## _Batch_ workflow

Batch workflows are located in the `.neuro/<batch-name>.yml` or `.neuro/<batch-name>.yaml` file under the flow's root. The config filename should be lowercase and not start with a digit if the [`id`](./#id) attribute is not specified. The following YAML attributes are supported:

## `kind`

**Required** The workflow _kind_, _must be_ `batch` _for batch_ workflows.

## `id`

**Expression contexts:** This attribute cannot contain expressions.

Identifier of the workflow. By default, the `id` is generated from the filename of the workflow config, with hyphens being (`-`) replaced with underscores (`_`). It's available as a `${{ flow.flow_id }}` in experssions.

## `title`

Workflow title.

**Expression contexts:** This attribute only allows expressions that don't access contexts.

## `defaults`

A map of default settings that will be applied to all tasks in the workflow. You can override these global default settings for specific tasks.

### `defaults.env`

A mapping of environment variables that are available to all tasks in the workflow. You can also set environment variables that are only available to a task. For more information, see [`tasks.env`](./#jobs-job-id-env).

When two or more environment variables are defined with the same name, `neuro-flow` uses the most specific environment variable. For example, an environment variable defined in a task will override the workflow default.

**Example**:

```yaml
env:
  SERVER: production
```

This attribute also supports dictionaries as values:

```yaml
env: ${{ {'global_a': 'val-a', 'global_b': 'val-b'} }}
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context).

### `defaults.life_span`

The default lifespan for jobs ran by the workflow. It can be overridden by [`tasks.life_span`](./#tasks-life\_span). If not set, the default task lifespan is 1 day. The lifespan value can be one of the following:

* A `float` number representing the amount of seconds (`3600` represents an hour)
* A string of the following format: `1d6h15m` (1 day, 6 hours, 15 minutes)

For lifespan-disabling emulation, use an arbitrary large value (e.g. `365d`). Keep in mind that this may be dangerous, as a forgotten job will consume cluster resources.

{% hint style="warning" %}
life span shorter than _1 minute_ is forbidden.
{% endhint %}

**Example:**

```yaml
defaults:
  life_span: 14d
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context).

### `defaults.preset`

The default preset name used by all tasks if not overridden by [`tasks.preset`](./#tasks-preset). The system-wide default preset is used if both `defaults.preset` and `tasks.preset` are omitted.

**Example:**

```yaml
defaults:
  preset: gpu-small
```

### `defaults.volumes`

Volumes that will be mounted to all tasks by default.

**Example:**

```yaml
defaults:
  volumes: 
    - storage:some/dir:/mnt/some/dir
    - storage:some/another/dir:/mnt/some/another/dir
```

Default volumes are not passed to actions.

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context).

### `defaults.schedule_timeout`

The default timeout for task scheduling. See [`tasks.schedule_timeout`](./#tasks-schedule\_timeout) for more information.

The attribute accepts the following values:

* A `float` number representing the amount of seconds (`3600` represents an hour)
* A string of the following format: `1d6h15m45s` (1 day, 6 hours, 15 minutes, 45 seconds).

The cluster-wide timeout is used if both `default.schedule_timeout` and `tasks.schedule_timeout` are omitted.

**Example:**

```yaml
defaults:
  schedule_timeout: 1d  # don't fail until tomorrow
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context).

### `defaults.tags`

A list of tags that are added to every task created by the workflow. A particular task definition can extend this global list by [`tasks.tags`](./#tasks-tags).

**Example:**

```yaml
defaults:
  tags: [tag-a, tag-b]
```

This attribute supports lists as values.

### `defaults.workdir`

The default working directory for tasks created by this workflow. See [`tasks.workdir`](./#tasks-workdir) for more information.

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context).

### `defaults.fail_fast`

When set to `true`, the system cancels all in-progress tasks if any one of them fails. It can be overridden by [`tasks.strategy.fail_fast`](./#tasks-strategy-fail\_fast). This is set to `true` by default.

**Example:**

```yaml
defaults:
  fail_fast: false
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context).

### `defaults.max_parallel`

The maximum number of tasks that can run simultaneously during flow execution. By default, there is no limit.

**Example:**

```yaml
defaults:
  max_parallel: 4
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context).

### `defaults.cache`

A mapping that defines how task outputs are cached. It can be overridden by [`tasks.cache`](./#tasks-cache)\`\`

### `defaults.cache.strategy`

The default strategy to use for caching. Available options are:

* `"none"` Don't use caching at all.
* `"default"` The basic caching algorithm that reuses cached outputs in case task definitions and all [expression contexts](../expression-syntax.md#contexts) available in the task's expressions are the same.

Default: `"default"`

**Example:**

```yaml
cache:
    strategy: "default"
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context).

### `defaults.cache.life_span`

The default cache invalidation duration. The attribute accepts the following values:

* A `float` number representing the amount of seconds (`3600` represents an hour)
* A string of the following format: `1d6h15m45s` (1 day, 6 hours, 15 minutes, 45 seconds)

Default: `14d` (two weeks).

{% hint style="info" %}
If you decrease this value and re-run the flow, `neuro-flow` will ignore cache entries that were added longer ago than the new `cache.life_span` value states.
{% endhint %}

**Example:**

```yaml
cache:
  life_span: 31d # Cache is valid for one month
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context).

## `images`

A mapping of image definitions used by the _batch_ workflow.

If the specified image reference is available at the Neu.ro registry and the [`.force_rebuild`](./#images-less-than-image-id-greater-than-force-rebuild) flag is not set, then Neu.ro Flow will not attempt to build the image from scratch. If this flag is set or the image is not in the registry, then the platform will start buliding the image.

{% hint style="info" %}
The `images` section is not required. A task can specify the image name in a plain string without referring to the `${{ images.my_image.ref }}` context.
{% endhint %}

### `images.<image-id>`

The key `image-id` is a string and its value is a map of an image's configuration data. You must replace `<image-id>` with a string that is unique to the `images` object. `<image-id>` must start with a letter and contain only alphanumeric characters or underscore symbols `_`. Dash `-` is not allowed.

### `images.<image-id>.ref`

**Required** Image _reference_ that can be used in the [`tasks.image`](./#tasks-image) expression.

**Example of a self-hosted image:**

```yaml
images:
  my_image:
    ref: image:my_image:latest
```

This can only use locally accessible functions (such as `hash_files`). Its value will be calculated before the remote executor starts.

**Example of external image:**

```yaml
images:
  python:
    ref: python:3.9.0
```

{% hint style="info" %}
Use the embedded [`hash_files()`](../../expression-functions.md#hash\_files-pattern) function to generate the built image's tag based on its content.
{% endhint %}

**Example of an auto-calculated stable hash:**

```yaml
images:
  my_image:
    ref: image:my_image:${{ hash_files('Dockerfile', 'requirements/*.txt', 'modules/**/*.py') }}
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context).

### `images.<image-id>.context`

The Docker _context_ used to build an image. Can be either local path (e.g. `${{ flow.workspace / 'some/dir' }}`) or a remote volume spec (e.g. `storage:subdir/${{ flow.flow_id }}`). If it's a local path, it cannot use anything that's not available at the beginning of a bake (for example, action inputs). If it's a remote path, usage of dynamic values is allowed. Local context will be automatically uploaded to storage during the "local actions" step of the bake.

**Example:**

```yaml
images:
  my_image:
    context: path/to/context
```

{% hint style="info" %}
`neuro-flow` cannot build images without the context, but can address _pre-built_ images using [`images.<image-id>.ref`](./#images-less-than-image-id-greater-than-ref)
{% endhint %}

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context).

### `images.<image-id>.dockerfile`

An optional Docker file name used for building images, `Dockerfile` by default.

Works almost the same as [`.context`](./#images-less-than-image-id-greater-than-context) - if it's a local path, dynamic values are forbidden and it's automatically uploaded. If it's a remote path, then dynamic values are allowed.

**Example:**

```yaml
images:
  my_image:
    dockerfile: MyDockerfile
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context).

### `images.<image-id>.build_args`

A list of optional build arguments passed to the image builder. See [Docker documentation](https://docs.docker.com/engine/reference/commandline/build/#set-build-time-variables---build-arg) for details. Supports dynamic values such as action inputs.

**Example:**

```yaml
images:
  my_image:
    build_args:
    - ARG1=val1
    - ARG2=val2
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context).

### `images.<image-id>.env`

A mapping of _environment variables_ passed to the image builder. Supports dynamic values such as action inputs.

**Example:**

```yaml
images:
  my_image:
    env:
      ENV1: val1
      ENV2: val2
```

This attribute also supports dictionaries as values:

```yaml
images:
  my_image:
    env: ${{ {'ENV1': 'val1', 'ENV2': 'val2'} }}
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context).

### `images.<image-id>.volumes`

A list of volume references mounted to the image building process. Supports dynamic values such as action inputs.

**Example:**

```yaml
images:
  my_image:
    volumes:
    - storage:folder1:/mnt/folder1:ro
    - storage:folder2:/mnt/folder2
```

This attribute also supports lists as values:

```yaml
images:
  my_image:
    volumes: ${{ ['storage:folder1:/mnt/folder1:ro', 'storage:folder2:/mnt/folder2'] }}
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context).

### `images.<image-name>.force_rebuild`

If this flag is enabled, the referenced image will be rebuilt from scratch for each bake.

**Example:**

```yaml
images:
  my_image:
    force_rebuild: true
```

## `params`

Mapping of key-value pairs that have default values.

This attribute describes a set of names and default values of parameters accepted by a flow.

Parameters can be specified in _short_ and _long_ forms.

The short form is compact but only allows to specify the names and default values of parameters:

```yaml
params:
  name1: default1
  name2: ~   # None by default
  name3: ""  # Empty string by default
```

The long form allows to additionally specify parameter descriptions. This can be useful for `neuro-flow bake` command introspection, shell autocompletion, and generation of more detailed error messages:

```yaml
params:
  name1:
    default: default1
    descr: The name1 description
  name2:
    default: ~
    descr: The name2 description
  name3:
    default: ""
    descr: The name3 description
```

This attribute can be overridden from the command line in two ways while running a batch in Neuro CLI:

* Specifying the parameters through `--param`.

```yaml
$ neuro-flow bake <batch-id> --param name1 val1 --param name2 val2
```

* Pointing to a YAML file with parameter descriptions through `--meta-from-file`.

```yaml
$ neuro-flow bake --meta-from-file <some-file>
```

The file should have the following structure:

```yaml
param1: value
param2: value
...
```

**Expression contexts:** This attribute only allows expressions that don't access contexts.

## `images`

A mapping of image definitions used by this workflow.

Unlike _live_ flow images, _batch_ flow images cannot be built using `neuro-flow build <image-id>`.

{% hint style="info" %}
The `images` section is not required. A task can specify the image name in a plain string without referring to the `${{ images.my_image.ref }}` context.

However, this section exists for convenience: there is no need to repeat yourself if you can just point the image reference everywhere in the YAML.
{% endhint %}

{% hint style="danger" %}
The following fields are disabled in _batch_ workflows and will be ignored:

* **`images.<image-id>.context`**
* **`images.<image-id>.dockerfile`**
* **`images.<image-id>.build_args`**
* **`images.<image-id>.env`**
* **`images.<image-id>.volumes`**
{% endhint %}

### `images.<image-id>`

The key `image-id` is a string and its value is a map of the task's configuration data. You must replace `<image-id>` with a string that is unique to the `images` object. `<image-id>` must start with a letter and contain only alphanumeric characters or underscore symbols `_`. Dash `-` is not allowed.

### `images.<image-id>.ref`

**Required** Image _reference_ that can be used in the `tasks.image` expression.

You can use the image definition to _address_ images hosted either on the Neu.ro registry or [_Docker Hub_](https://hub.docker.com/search?q=\&type=image).

**Example:**

```yaml
images:
  my_image:
    ref: image:my_image:latest # Neu.ro registry hosted iamge 
  python:
    ref: python:3.9.0 # Docker Hub hosted image
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context).

## `volumes`

A mapping of volume definitions available in this workflow. A volume defines a link between the Neu.ro storage folder and a remote folder that can be mounted to a task.

Unlike _live_ flow volumes, _batch_ flow volumes **cannot** be synchronized by `neuro-flow upload` and `neuro-flow download` commands. They can only be mounted to a task by using `task.volumes` attribute.

{% hint style="danger" %}
The following fields are disabled in _batch_ workflows and will cause an error:

* **`volumes.<volume-id>.local`**
{% endhint %}

### `volumes.<volume-id>`

The key `volume-id` is a string and its value is a map of the volume's configuration data. You must replace `<volume-id>` with a string that is unique to the `volumes` object. The `<volume-id>` must start with a letter and contain only alphanumeric characters or underscore symbols `_`. Dash `-` is not allowed.

### `volumes.<volume-id>.remote`

**Required** Volume URI on the Neu.ro Storage.

**Example:**

```yaml
volumes:
  folder:
    remote: storage:path/to/folder
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context).

### `volumes.<volume-id>.mount`

**Required** Mount path inside a task.

**Example:**

```yaml
volumes:
  folder:
    mount: /mnt/folder
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context).

### `volumes.<volume-id>.read_only`

The volume is mounted as _read-only_ by default if this attribute is enabled, _read-write_ mode is used otherwise.

**Example:**

```yaml
volumes:
  folder:
    read_only: true
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context).

## `tasks`

List of tasks and action calls that this batch workflow contains. Unlike jobs in live workflows, all tasks are executed with one command in the order specified by [`tasks.needs`](./#tasks-needs). To start execution, run `neuro-flow bake <batch-id>`.

**Example:**

```yaml
tasks:
  - id: task_1
  - id: task_2 
  - id: task_3
```

## Attributes for tasks and action calls

The attributes described in this section can be applied both to plain tasks and action calls. To simplify reading, this section uses the term "task" instead of "task or action call".

### `tasks.id`

A unique identifier for the task. It's used to reference the task in [`tasks.needs`](./#tasks-needs). The value must start with a letter and only contain alphanumeric characters or underscore symbols (`_`). The dash symbol (`-`) is not allowed.

{% hint style="info" %}
It is impossible to refer to tasks without an ID inside the workflow file, but you can refer to them as `task-<num>` in the command line output. Here, `<num>` is an index from the [`tasks`](./#tasks) list.
{% endhint %}

**Expression contexts:** [`matrix` context](batch-contexts.md#matrix-context).

### `tasks.needs`

An array of strings identifying all tasks that must be completed or running before this task will run. If a task fails, all tasks that need it are skipped unless the task uses a [`tasks.enable`](./#tasks-enable) statement that causes it to ignore the dependency failure.\
By default, `tasks.needs` is set to the previous task in the [`tasks`](./#tasks) list. In case the previous task has [`matrix`](./#tasks-strategy-matrix) enabled, the current task will only run after all matrix tasks are completed.\
This property also specifies what entries are available in the [needs context](batch-contexts.md#needs-context).

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

The order is the same as in the default behavior without `needs`.

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

1. task\_1 and task\_2 (simultaneously)
2. task\_3

**Example 3**

```yaml
tasks:
  - id: task_1  
  - id: task_2
    needs: [] 
  - id: task_3
    needs: 
      task_1: running
      task_2: running
```

Here, task\_3 will only be executed if task\_1 and task\_2 are already running.

The following are two different ways to specify needed tasks:

```yaml
needs:
  task_1: running
```

```yaml
needs:
  ${{ 'task_1' }}: running
```

The possible task states are `running` and `completed`.

{% hint style="info" %}
You can use `neuro-flow inspect --view BAKE_ID` to view the graph of running batch tasks converted to a PDF file.
{% endhint %}

**Expression contexts:** [`matrix` context](batch-contexts.md#matrix-context).

### `tasks.enable`

The flag that prevents a task from running unless a condition is met. To learn how to write conditions, refer to [expression syntax](../expression-syntax.md). Default: `${{ success() }}`

**Example:**

```yaml
tasks:
  - enable: ${{ always() }} # Run this task in any case 
  - enable: ${{ flow.id == "some-value" }} # Simple condition
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).

### `tasks.strategy`

A mapping that defines a matrix and some auxiliary attributes to run multiple instances of the same task.

### `tasks.strategy.matrix`

The `matrix` attribute defines a set of configurations with which to run a task. Each key in this mapping sets some variable that will be available in the `matrix` context in expressions of the corresponding task. Each value should be an array, and `neuro-flow` will start task variants with all possible combinations of items from these arrays. The matrix can generate 256 different tasks at most.

**Example 1:**

```yaml
id: example_${{ matrix.param }}
strategy:
  matrix:
    param: [a, b]
```

In this example, tasks with IDs `example_a` and `example_b` will be generated.

**Example 2:**

```yaml
id: ${{ matrix.param1 }}_${{ matrix.param2 }}
strategy:
  matrix:
    param1: [a, b]
    param2: [x, y]
```

In this example, tasks with IDs `a_x`, `a_y`, `b_x`, `b_y` will be generated.

{% hint style="info" %}
Auto-generated IDs for matrix tasks will have suffixes in the form of `-<param-1>-<param-2>`
{% endhint %}

**Expression contexts:** Matrix values only allows expressions that don't access contexts.

### `tasks.strategy.matrix.exclude`

`exclude` is a list of combinations to remove from the matrix. These entries can be partial, in which case all matching combinations are excluded.

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

In this example, tasks with IDs `a_x_2`, `a_y_1`, `a_y_2`, `b_x_1`, `b_x_2` will be generated.

**Expression contexts:** Matrix values only allows expressions that don't access contexts.

### `tasks.strategy.matrix.include`

`include` is a list of combinations to add to the matrix. These entries cannot be partial. In case [`exclude`](./#tasks-strategy-matrix-exclude) is also set, `include` will be applied after it.

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

In this example, tasks with IDs `a_x`, `a_y`, `b_x`, `b_y`, `a_z` will be generated.

**Expression contexts:** Matrix values only allows expressions that don't access contexts.

### `tasks.strategy.fail_fast`

When set to `true`, the system cancels all in-progress tasks if this task or any of its matrix tasks fail. Default: `true`.

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`strategy` context](batch-contexts.md#strategy-context) (contains flow global values).

### `tasks.strategy.max_parallel`

The maximum number of matrix tasks that can run simultaneously. By default, there is no limit.

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`strategy` context](batch-contexts.md#strategy-context) (contains flow global values).

### `tasks.cache`

A mapping that defines how task outputs are cached.

### `tasks.cache.strategy`

The strategy to use for caching of this task. Available options are:

* `"none"` Don't use caching at all
* `"inherit"` Use the flow default value from [`defaults.cache.stategy`](./#defaults-cache-strategy)\`\`
* `"default"` The basic caching algorithm that reuses cached outputs in case task definition and all [expression contexts](../expression-syntax.md#contexts) available in task expressions are the same.

Default: `"inherit"`

**Example:**

```yaml
cache:
    strategy: "none"
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context).

### `tasks.cache.life_span`

The cache invalidation duration. This attribute can accept the following values:

* A `float` number representing an amount of seconds
* A string in the following format: `1d6h15m45s` (1 day, 6 hours, 15 minutes, 45 seconds)

Defaults to [`defaults.cache.life_span`](./#defaults-cache-life\_span) if not specified.

{% hint style="info" %}
If you decrease this value and re-run the flow, `neuro-flow` will ignore cache entries that were added longer ago than the new `cache.life_span` value specifies.
{% endhint %}

**Example:**

```yaml
cache:
  life_span: 31d # Cache is valid for one month
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context).

## Attributes for tasks

The attributes in this section are only applicable to plain tasks that are executed by running Docker images on the Neu.ro platform.

### `tasks.image`

**Required** Each task is executed remotely on the Neu.ro cluster using a _Docker image_. The image can be hosted on [_Docker Hub_](https://hub.docker.com/search?q=\&type=image) (`python:3.9` or `ubuntu:20.04`) or on the Neu.ro Registry (`image:my_image:v2.3`).

**Example with a constant image string:**

```yaml
tasks:
  - image: image:my_image:v2.3
```

You may often want to use the reference to [`images.<image-id>`](../live-workflow-syntax/#images-less-than-image-id-greater-than).

**Example with a reference to the `images` section:**

```yaml
tasks:
  - image: ${{ images.my_image.ref }}
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).

### `tasks.cmd`

A tasks executes either a _command_, a _bash_ script, or a _python_ script. The `cmd`, `bash`, and `python` are **mutually exclusive**: only one of the three is allowed at the same time. If none of these three attributes are specified, the [`CMD`](https://docs.docker.com/engine/reference/builder/#cmd) from the [`tasks.image`](./#tasks-image) is used.

The `cmd` attribute points to the command with optional arguments that is available in the executed `tasks.image`.

**Example:**

```yaml
tasks:
  - cmd: tensorboard --host=0.0.0.0
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).

### `tasks.bash`

This attribute contains a `bash` script to run.

Using `cmd` to run a bash script can be tedious: you need to apply quotas to the executed script and set proper bash flags to fail on error.

The `bash` attribute is essentially a shortcut for `cmd: bash -euo pipefail -c <shell_quoted_attr>` .

This form is especially handy for executing complex multi-line bash scripts.

`cmd`, `bash`, and `python` are **mutually exclusive**.

`bash` should be pre-installed on the image to make this attribute work.

**Example:**

```yaml
tasks:
  - bash: |
      for arg in {1..5}
      do
        echo "Step ${arg}"
        sleep 1
      done
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).

### `tasks.python`

This attribute contains a `python` script to run.

Python is usually considered to be one of the best languages for scientific calculation. If you prefer writing simple inlined commands in `python` instead of `bash`, this notation is great for you.

The `python` attribute is essentially a shortcut for `cmd: python3 -uc <shell_quoted_attr>` .

`cmd`, `bash`, and `python` are **mutually exclusive**.

`python3` should be pre-installed on the image to make this attribute work.

**Example:**

```yaml
tasks:
  - python: |
      import sys
      print("The Python version is", sys.version)
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).

### `tasks.entrypoint`

You can override the Docker image [`ENTRYPOINT`](https://docs.docker.com/engine/reference/builder/#entrypoint) if needed or specify one. Unlike the Docker `ENTRYPOINT` instruction that has a shell and exec form, the `entrypoint` attribute only accepts a single string defining the executable to be run.

**Example:**

```yaml
tasks:
  - entrypoint: sh -c "Echo $HOME"
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).

### `tasks.env` <a href="#jobs-job-id-env" id="jobs-job-id-env"></a>

Sets environment variables to use in the executed task.

When two or more variables are defined with the same name, `neuro-flow` uses the most specific environment variable. For example, an environment variable defined in a task will override the [workflow default](./#defaults-env).

**Example:**

```yaml
tasks:
  - env:
      ENV1: val1
      ENV2: val2
```

This attribute also supports dictionaries as values:

```yaml
tasks:
  env: ${{ {'global_a': 'val-a', 'global_b': 'val-b'} }}
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).

### `tasks.http_auth`

Control whether the HTTP port exposed by the tasks requires the Neu.ro Platform authentication for access.

You may want to disable the authentication to allow everybody to access your task's exposed web resource.

By default, tasks have HTTP protection enabled.

**Example:**

```yaml
tasks:
  - http_auth: false
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).

### `tasks.http_port`

The number of the task's HTTP port that will be exposed globally.

By default, the Neu.ro Platform exposes the task's internal `80` port as an HTTPS-protected resource.

You may want to expose a different local port. Use `0` to disable the feature entirely.

**Example:**

```yaml
tasks:
  - http_port: 8080
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).

### `tasks.life_span`

The time period after which a task will be automatically killed.

By default, tasks live 1 day. You may want to change this period by customizing the attribute.

The value could be:

* A float number representing an amount of seconds (`3600` for an hour)
* An expression in the following format: `1d6h15m` (1 day, 6 hours, 15 minutes)

Use an arbitrary large value (e.g. `365d`) for lifespan-disabling emulation. Keep in mind that this can be dangerous, as a forgotten task will consume cluster resources.

**Example:**

```yaml
tasks:
  - life_span: 14d12h
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).

### `tasks.name`

Allows you to specify a task's name. This name becomes a part of the task's internal hostname and exposed HTTP URL, and the task can then be controlled by its name through the low-level `neuro` tool.

The name is completely _optional_, the `neuro-flow` tool doesn't require it to work properly.

**Example:**

```yaml
task:
  - name: my-name
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).

### `tasks.pass_config`

Set this attribute to `true` if you want to pass the Neu.ro config used to execute `neuro-flow run ...` command into the spawned task. This can be useful if you use a task image with Neuro CLI installed and want to execute `neuro ...` commands _inside_ the running task.

By default, the config is not passed.

**Example:**

```yaml
tasks:
  - pass_config: true
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).

### `tasks.preset`

The preset to execute the task with.

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).

### `tasks.schedule_timeout`

Use this attribute if you want to increase the _schedule timeout_. This will prevent a task from failing if the Neu.ro cluster is under high load and requested resources are likely to not be available at the moment.

If the Neu.ro cluster has no resources to launch a task immediately, this task is pushed into the waiting queue. If the task is not started yet at the end of the _schedule timeout_, it will be failed.

The default system-wide _schedule timeout_ is controlled by the cluster administrator and is usually about 5-10 minutes.

The value of this attribute can be:

* A `float` number representing an amount of seconds
* A string in the following format: `1d6h15m45s` (1 day, 6 hours, 15 minutes, 45 seconds)

**Example:**

```yaml
tasks:
  - schedule_timeout: 1d  # don't fail until tomorrow
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).

### `tasks.tags`

A list of additional task tags.

Each task is tagged. A task's tags are taken from this attribute and system tags (`project:<project-id>`, `flow:<flow-id>`, and `task:<task-id>`).

**Example:**

```yaml
task:
  - tags:
    - tag-a
    - tag-b
```

This attribute also supports lists as values:

```yaml
task:
  tags: ${{ ['tag-a', 'tag-b'] }}
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).

### `tasks.title`

A task's title. The title is equal to `<task-id>` if not overridden.

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).

### `tasks.volumes`

A list of task volumes. You can specify a plain string for the volume reference or use the `${{ volumes.<volume-id>.ref }}` expression.

**Example:**

```yaml
tasks:
  - volumes:
    - storage:path/to:/mnt/path/to
    - ${{ volumes.my_volume.ref }}
```

This attribute also supports lists as values:

```yaml
tasks:
  volumes: ${{ ['storage:path/to:/mnt/path/to', volumes.my_volume.ref] }}
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).

### `tasks.workdir`

A working directory to use inside the task.

This attribute takes precedence if specified. Otherwise, the [`WORKDIR`](https://docs.docker.com/engine/reference/builder/#workdir) definition from the image is used.

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).

## Attributes for actions calls

The attributes described in this section are only applicable to action calls. An action is a reusable part that can be integrated into a workflow. Refer to the [actions reference](../actions-syntax/) to learn more about actions.

### `tasks.action`

A URL that selects an action to run. It supports two schemes:

* `workspace:` or `ws:` for action files that are stored locally
* `github:` or `gh:` for actions that are bound to a Github repository

The `ws:` scheme expects a valid filesystem path to the action file.

The `gh:` scheme expects the following format: `{owner}/{repo}@{tag}`. Here, `{owner}` is the owner of the Github repository, `{repo}` is the repository's name, and `{tag}` is the commit tag. Commit tags are used to allow versioning of actions.

**Example of the `ws:` scheme**

```yaml
tasks:
  - action: ws:path/to/file/some-action.yml
```

**Example of the `gh:` scheme**

```yaml
tasks:
  - action: gh:username/repository@v1
```

**Expression contexts:** This attribute only allows expressions that don't access contexts.

### `tasks.args`

Mapping of values that will be passed to the actions as arguments. This should correspond to [`inputs`](../actions-syntax/#inputs) defined in the action file.

**Example:**

```yaml
tasks:
  - args:
      param1: value1          # You can pass constant
      param2: ${{ flow.id }}  # Or some expresion value
```

**Expression contexts:** [`flow` context](batch-contexts.md#flow-context), [`params` context](batch-contexts.md#params-context), [`env` context](batch-contexts.md#env-context), [`tags` context](batch-contexts.md#tags-context), [`volumes` context](batch-contexts.md#volumes-context), [`images` context](batch-contexts.md#images-context), [`matrix` context](batch-contexts.md#matrix-context), [`strategy` context](batch-contexts.md#strategy-context), [`needs` context](batch-contexts.md#needs-context).
