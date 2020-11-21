# Batch workflow syntax

## _Batch_ workflow

The batch workflow is located at `.neuro/<batch-name>.yml` file under the project root;`.neuro/<batch-name>.yaml` is also supported if you prefer a longer suffix for some reason. The config filename should not start with a digit and be lowercase if the [`id`](batch-workflow-syntax.md#id) attribute is not specified. The following YAML attributes are supported:

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

Params is a mapping of key-value pairs that have default value and could be overridden from a command line by using `neuro-flow bake <batch-id> --param name1 val1 --param name2 val2`

This attribute describes a set of param names accepted by a flow and their default values. 

The parameter can be specified in a _short_ and _long_ form.    
  
The short form is compact but allows to specify the parameter name and default value only:

```yaml
params:
  name1: default1
  name2: ~   # None by default
  name3: ""  # Empty string by default
```

The long form allows to point the parameter description also \(can be useful for `neuro-flow bake` command introspection, the shell autocompletion, and generation a more verbose error message if needed:

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

Both examples above are equal but the last has parameter descriptions.

## `images`

A mapping of image definitions used by this workflow.

Unlike _live_ flow images, _batch_ flow images cannot be build using `neuro-flow build <image-id>`. 

{% hint style="info" %}
The `images` section is not required, a task can specify the image name as a plain string without referring to `${{ images.my_image.ref }}` context.

The section exists for convenience: there is no need to repeat yourself if you can just point the image ref everywhere in the YAML.
{% endhint %}

{% hint style="danger" %}
The following fields are disabled in _batch_ flow and will be ignored:

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

### `tasks.cache.life_span`

The cache invalidation duration. The attribute accepts either a `float` number of seconds or a string in`1d6h15m45s` \(1 day 6 hours, 15 minutes, 45 seconds\). Defaults to [`defaults.cache.life_span`](batch-workflow-syntax.md#defaults-cache-life_span) if not specified.

{% hint style="info" %}
If you decrease this value and re-run flow, `neuro-flow` will ignore cache entries that were added more than the new value of`cache.life_span` seconds ago.  
{% endhint %}

**Example:**

```yaml
cache:
  life_span: 31d # Cache is valid for one month
```

###  `tasks.image`

**Required** Each task is executed remotely on the Neu.ro cluster using a _Docker image_. The image can be hosted on [_Docker Hub_](https://hub.docker.com/search?q=&type=image) \(`python:3.9` or `ubuntu:20.04`\) or on the Neu.ro Registry \(`image:my_image:v2.3`\).

**Example with a constant image string:**

```yaml
tasks:
  - image: image:my_image:v2.3
```

Often you want to use the reference to [`images.<image-id>`](live-workflow-syntax.md#images-less-than-image-id-greater-than).

**Example with a reference to `images` section:**

```yaml
tasks:
  - image: ${{ images.my_image.ref }}
```

### `tasks.cmd`

A tasks executes either a _command_, or _bash_ script, or _python_ script. The `cmd`, `bash,` and `python` are **mutually exclusive**: only one of three is allowed. If none of these three attributes are specified the [`CMD`](https://docs.docker.com/engine/reference/builder/#cmd) from the [`tasks.image`](batch-workflow-syntax.md#tasks-image) is used.

`cmd` attribute points on the command with optional arguments which is available in the executed `tasks.image` .

**Example:**

```yaml
tasks:
  - cmd: tensorboard --host=0.0.0.0
```

### `tasks.bash`

The attribute contains a `bash` script to run. 

Using `cmd` to run bash script is tedious: you need to apply quotas to the executed script and setup the proper bash flags to fail on error.

The `bash` attribute is essentially a shortcut for `cmd: bash -euo pipefail -c <shell_quoted_attr>` .

This form is especially handy for executing multi-line complex bash scripts.

The `cmd`, `bash,` and `python` are **mutually exclusive**.

The `bash` should be pre-installed in the image to make this attribute work.

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

### `tasks.python`

The attribute contains a `python` script to run.

Python is the language number one for modern scientific calculations.  If you prefer writing simple inlined commands in `python` instead  of `bash` this notation is developed for you.

The `python` attribute is essentially a shortcut for `cmd: python3 -uc <shell_quoted_attr>` .

The `cmd`, `bash,` and `python` are **mutually exclusive**.

The `python3` should be pre-installed in the image to make this attribute work.

**Example:**

```yaml
tasks:
  - python: |
      import sys
      print("The Python version is", sys.version)
```

### `tasks.entrypoint`

You can override the Docker image [`ENTRYPOINT`](https://docs.docker.com/engine/reference/builder/#entrypoint) if needed  or sets it if one wasn't already specified. Unlike the Docker `ENTRYPOINT` instruction which has a shell and exec form, `entrypoint` attribute accepts only a single string defining the executable to be run.

**Example:**

```yaml
tasks:
  - entrypoint: sh -c "Echo $HOME"
```

### `tasks.env` <a id="jobs-job-id-env"></a>

Sets environment variables to use in the executed task. 

**Example:**

```yaml
tasks:
  - env:
      ENV1: val1
      ENV2: val2
```

### `tasks.http_auth`

Control whether the HTTP port exposed by the tasks requires the Neu.ro Platform authentication for access.

You can want to disable the authentication to allow everybody to access your task's exposed web resource.

The task has HTTP protection by default.

**Example:**

```yaml
tasks:
  - http_auth: false
```

### `tasks.http_port`

The task HTTP port number to expose globally.

By default, the Neu.ro Platform exposes the task's internal `80` port as HTTPS protected resource.

You may want to expose a different local port. Use `0` to disable the feature entirely.

**Example:**

```yaml
tasks:
  - http_port: 8080
```

### `task.life_span`

The time period at the end of the task will be automatically killed.

By default, the task lives 1 day.

You may want to increase this period by customizing the attribute.

The value is a float number of seconds \(`3600` for an hour\) or expression in the following format: `1d6h15m` \(1 day 6 hours, 15 minutes\). Use an arbitrary huge value \(e.g. `365d`\) for the life-span disabling emulation \(it can be dangerous, a forgotten task consumes the cluster resources\).

**Example:**

```yaml
tasks:
  - life_span: 14d12h
```

### `task.name`

You can specify the task's name if needed.  The name becomes a part of the task's internal hostname and exposed HTTP URL, the task can be controlled by its name when low-level `neuro` tool is used.

The name is _optional_, `neuro-flow` tool doesn't need it.

**Example:**

```yaml
task:
  - name: my-name
```

### `tasks.pass_config`

Set the attribute to `true` if you want to pass the Neuro current config used to execute `neuro-flow bake ...` command into the spawn task. It can be useful if you uses a task image with Neuro CLI installed and want to execute `neuro ...` commands _inside_ the running task.

By default the config is not passed.

**Example:**

```yaml
tasks:
  - pass_config: true
```

### `tasks.preset`

The preset name to execute the task with. 

### `tasks.schedule_timeout`

Use this attribute if you want to increase the _schedule timeout_ to prevent the task from failing if the Neu.ro cluster is under high load and requested resources a not available at the moment highly likely.  

If the Neu.ro cluster has no resources to launch a task immediately the task is pushed into the wait queue. If the task is not started yet at the moment of _schedule timeout_ expiration the task is failed.

The default system-wide _schedule timeout_ is controlled by the cluster administrator and usually is about 5-10 minutes.  If you want to **&lt;MISSING PART&gt;**

The attribute accepts either a `float` number of seconds or a string in`1d6h15m45s` \(1 day 6 hours, 15 minutes, 45 seconds\).

**Example:**

```yaml
tasks:
  - schedule_timeout: 1d  # don't fail until tomorrow
```

### `tasks.tags`

A list of additional task tags. 

Each task is tagged. The tasks tags are from tags enumerated by this attribute and system tags \(`project:<project-id>`, `flow:<flow-id>` and `task:<task-id>`\). 

**Example:**

```yaml
task:
  - tags:
    - tag-a
    - tag-b
```

### `task.title`

The task title. The title is equal to `<task-id>` if not overridden.

### `task.volumes`

A list of task volumes. You can specify a bare string for the volume reference or use `${{ volumes.<volume-id>.ref }}` expression.

**Example:**

```yaml
tasks:
  - volumes:
    - storage:path/to:/mnt/path/to
    - ${{ volumes.my_volume.ref }}
```

### `task.workdir`

The current working dir to use inside the task.

This attribute takes precedence if set. Otherwise a [`WORKDIR`](https://docs.docker.com/engine/reference/builder/#workdir) definition from the image is used.

