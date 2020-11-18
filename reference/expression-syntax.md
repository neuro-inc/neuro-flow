# Expression syntax

`neuro-flow` allows writing custom expressions in YAML configuration files.

## About contexts and expressions

You can use expressions to programmatically set variables in workflow files and access contexts. An expression can be any combination of literal values, references to a context, or functions. You can combine literals, context references, and functions using operators.

You need to use specific syntax to tell GitHub to evaluate an expression rather than treat it as a string.

```text
${{ <expression> }}
```

### Example setting an environment variable:

```yaml
env:
  my_env_var: ${{ <expression> }}
```

{% hint style="info" %}
Sometimes curly brackets conflict with other tools in your toolchain. For example, `cookiecutter` uses `Jinja2` templates which also uses curly brackets for template formatting.

In this case, `neuro-flow` accepts square brackets syntax for expressions: `$[[ <expression> ]]`. Both notations are equal and interchangeable.
{% endhint %}

## Contexts

Contexts are a way to access information about workflow runs, jobs, tasks, volumes, images, etc. Contexts use the expression syntax.

```yaml
${{ <context> }}
```

There are two main sets of contexts: one is available for _live_ mode and another one exists for _batch_ mode. Additionally, actions can access a specific namespace with contexts that similar but slightly different from ones from the main workflow. The following chapters describe all mentioned context namespaces in detail.

## Live Contexts

| Context name | Description |
| :--- | :--- |
| flow | Information about the main workflow settings, defaults, etc. See &lt;link&gt; for details |
| env | Contains environment variables set in a workflow or job. For more information, see [`env` context](https://docs.github.com/en/free-pro-team@latest/actions/reference/context-and-expression-syntax-for-github-actions#env-context) . |
| tags | A set of job tags set in a workflow or job |
| volumes | Contains a mapping of volumes and secret files. |
| images | Contains a mapping of images on the Neu.ro registry. |
| params | A mapping of workflow-global parameters \(see also &lt;params&gt; section in YAML\). |
| multi | Multi-job context. |
|  |  |
|  |  |
|  |  |
|  |  |

### `flow` context

The `flow`context contains information about the workflow: it's id, title, etc.

| Property name | Type | Description |
| :--- | :--- | :--- |
| flow\_id | str | The workflow id. It is auto-calculated from the workflow's YAML filename with a dropped suffix. You can override the `flow_id` by providing &lt;link&gt; attribute in YAML file. |
| project\_id | str |  |
| workspace | LocalPath |  |
| title | str |  |

