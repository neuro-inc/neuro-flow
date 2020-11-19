# Batch workflow syntax

## _Batch_ workflow

The batch workflow is located at `.neuro/<batch-name>.yml` file under the project root;`.neuro/<batch-name>.yaml` is also supported if you prefer a longer suffix for some reason. The config filename should valid identifier if the [`id`](batch-workflow-syntax.md#id) attribute is not specified. The following YAML attributes are supported:

## `kind`

**Required** The workflow _kind_, _must be_ `batch` _for batch_ workflows.

## `id`

Identifier of the workflow. By default, the `id` is workflow config filename without extension with  hyphens \(`-`\) replaced with underscores \(`_`\).

## `title`

Workflow title

## `defaults`

A map of default settings that will apply to all tasks in the workflow. You can override these global default settings for a particular task.

### `defaults.fail_fast`

When set to `true`, the system cancels all in-progress jobs if any job fails. Default: `true`

```yaml
defaults:
  fail_fast: False
```

### `defaults.max_parallel`

The maximum number of jobs that can run simultaneously during flow execution. By default, there is no limit.

**Example:**

```yaml
defaults:
  max_parallel: 4
```

### `defaults.cache`

A mapping that defines how task outputs caching works. 

## `defaults.cache.strategy`

The default strategy to use for caching. Available options are:

* `"none"` Do not use caching at all 
* `"default"` The basic caching algorithm, that reuses cached outputs in case task definition and all [expression contexts](expression-syntax.md#contexts) available in task expressions are the same.

Default value is `"default"`.

**Example:**

```yaml
cache:
    strategy: "default"
```

### `defaults.cache.life_span`

The default cache invalidation duration. The attribute accepts either a `float` number of seconds or a string in`1d6h15m45s` \(1 day 6 hours, 15 minutes, 45 seconds\). Default value is `14d` \(two weeks\)

{% hint style="info" %}
If you decrease this value and re-run flow, `neuro-flow` will ignore cache entries that were added more than new`cache.life_span` ago.  
{% endhint %}

**Example:**

```yaml
cache:
  life_span: 31d # Cache is valid for one month 
```

## `params`

Params is a mapping of key-value pairs that have a default value and could be overridden from a command line by using `neuro-flow bake <batch-name> --param NAME1 val1 --param NAME2 val2`

## `params.<param-name>.default`

The default value to use when param is not overrideen from a command line.

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

## `params.<param-name>.descr`

The human-readable description of the param. 

**Example:**

```yaml
params:
  my-param: 
    descr: This is param description 
```

## tasks

List of tasks that this batch workflow contains. Unlike jobs in the live workflow, all tasks are executed with one command in order that specified by [`tasks.needs`](batch-workflow-syntax.md#tasks-needs) . To start execution, run `neuro-flow bake <batch-filename>`.

**Example:**

```yaml
tasks:
  - id: task_1
  - id: task_2 
  - id: task_3
```

## tasks.id

 A unique identifier for the task. It is used to reference the task in [`tasks.needs`](batch-workflow-syntax.md#tasks-needs). The value must start with a letter and contain only alphanumeric characters or `_`. Dash `-` is not allowed.

## tasks.needs

The array of strings identifying all tasks that must complete successfully before this task will run. If a task fails, all tasks that need it are skipped unless the tasks use a [`tasks.enable`](batch-workflow-syntax.md#tasks-enable) statement that causes the task to ignore dependency failure.  
By default, `tasks.needs` is set to the previous task in the [`tasks`](batch-workflow-syntax.md#tasks) list. In case the previous task has[`matrix`](batch-workflow-syntax.md#tasks-strategy-matrix) set, the task will only run after all matrix tasks are completed.  
This property also specifies what entries are available in needs &lt;link here&gt; context.

**Example 1:**

```yaml
tasks:
  - id: task_1  
  - id: task_2
    needs: [tasks_1] 
  - id: task_3
    needs: [tasks_2]
```

In this case, tasks will execute in the following order:

1. task\_1
2. task\_2
3. task\_3

This is the same as default behaviour \(without `needs`\)  
  
**Example 2:**

```yaml
tasks:
  - id: task_1  
  - id: task_2
    needs: [] 
  - id: task_3
    needs: [task_1, tasks_2]
```

In this case, tasks will execute in the following order:

1. task\_1 and task\_2 \(simultaneously\)
2. task\_3

{% hint style="info" %}
You can use `neuro-flow inspect --view BAKE_ID` to view tasks graph of running batch rendered to pdf.
{% endhint %}

## tasks.enable



## tasks.strategy

## tasks.strategy.matrix

## tasks.strategy.matrix.exclude

## tasks.strategy.matrix.include

## tasks.strategy.fail\_fast

## tasks.strategy.max\_parallel

## 

## tasks.cache

####  ExecUnit options are the same as for jobs

