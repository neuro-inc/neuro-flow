# Expression syntax

`neuro-flow` allows writing custom expressions in YAML configuration files.

## About contexts and expressions

You can use expressions to programmatically set variables in workflow files and access contexts. An expression can be any combination of literal values, references to a context, or functions. You can combine literals, context references, and functions with the help of operators.

You need to use specific syntax to tell Neuro Flow to evaluate an expression rather than to treat it as a string.

```
${{ <expression> }}
```

### Example - setting an environment variable:

```yaml
env:
  my_env_var: ${{ <expression> }}
```

{% hint style="info" %}
Sometimes curly brackets conflict with other tools in your toolchain. For example, `cookiecutter` uses `Jinja2` templates which also uses curly brackets for template formatting.

In this case, `neuro-flow` accepts the square brackets syntax for expressions: `$[[ <expression> ]]`. Both notations are equal and interchangeable.
{% endhint %}

## Contexts

Contexts are a way to access information about workflow runs, jobs, tasks, volumes, images, etc. Contexts use the expression syntax.

```yaml
${{ <context> }}
```

There are two main sets of contexts: one is available for _live_ mode and another one for _batch_ mode. Additionally, actions can access a specific namespace with contexts that are similar but slightly different from ones from the main workflow. The following chapters describe all mentioned context namespaces in detail. Refer to [live contexts](live-workflow-syntax/live-contexts.md), [batch contexts](batch-workflow-syntax/batch-contexts.md), and [actions contexts](actions-syntax/live-actions-contexts.md) for details.

## Property access

You can access properties of contexts and other objects using one of the following syntaxes:

* Index syntax: `flow['workspace']`
* Property dereference syntax: `flow.workspace`

In order to use property dereference syntax, the property name must:

* start with a letter`a-Z`.
* be followed by a letter `a-Z`, digit `0-9` or underscore `_`.

## Literals

As part of an expression, you can use `None`, `bool`, `int`, `float`, or `string` data types.

| Data type | Literal value                                                                                                                                                     |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `None`    | `None`                                                                                                                                                            |
| `boolean` | `True` or `False`(case sensitive).                                                                                                                                |
| `int`     | <p>Any integer defined by either decimal (<code>42</code>), hex (<code>0xFF</code>), octal (<code>0o22</code>), or binary</p><p>(<code>0b1011</code>) format.</p> |
| `float`   | A real number that contains digits after the period. Exponential notation is also supported.                                                                      |
| `string`  | You can use either single or double quotes for strings.                                                                                                           |

**Example**

```
env:
  NoneValue: ${{ None }}
  boolValue: ${{ False }}
  intValue: ${{ 42 }}
  intHexValue: ${{ 0xff }}
  intOctalValue: ${{ 0o22}}
  intBinaryValue: ${{ 0b1011 }}
  floatValue: ${{ 0.22 }}
  floatExponentialValue: ${{ 1-e10 }}
  stringValue: ${{ "String with single quote: ' " }}
```

## Operators

| Operator | Description           |
| -------- | --------------------- |
| `( )`    | Logical grouping      |
| `not`    | Not                   |
| `<`      | Less than             |
| `<=`     | Less than or equal    |
| `>`      | Greater than          |
| `>=`     | Greater than or equal |
| `==`     | Equal                 |
| `!=`     | Not equal             |
| `and`    | And                   |
| `or`     | Or                    |

## Lists and dictionaries

You can use lists and dictionaries in expressions.

**Example**

```
env:
  list: ${{ [ value1, value2, value3 ] }}
  emptyList: ${{ [] }}
  dict: ${{ { "key1": "value1", "key2": "value2" } }}
  emptyDict: ${{ {} }}
```

## Functions

To allow some operations in expressions, Neu.ro provides a set of built-in functions. The function call syntax is the following:

```
${{ function_name(arg1, arg2, arg3) }}
```

When a function returns an object as the result, you can access properties as usual:

```
${{ parse_json('{"name": "value"}').name }}
```

Check the [functions reference](../expression-functions.md) for the list of available functions.
