# Expression functions

## Basic functions

All expressions (`${{ <expression }}`) support a set of pre-built functions:

| Function name                                                   | Description                                                              |
| --------------------------------------------------------------- | ------------------------------------------------------------------------ |
| [len()](expression-functions.md#len-s)                          | Return the length of the argument.                                       |
| [keys()](expression-functions.md#keys-dictionary)               | Return the keys of the dictionary.                                       |
| [lower()](expression-functions.md#lower-string)                 | Convert a string to lowercase.                                           |
| [upper()](expression-functions.md#upper-string)                 | Convert a string to uppercase.                                           |
| [fmt()](expression-functions.md#fmt-format\_string-arg-1)       | Perform string formatting.                                               |
| [to\_json()](expression-functions.md#to\_json-data)             | Convert an object to a JSON string.                                      |
| [from\_json()](expression-functions.md#from\_json-json\_string) | Convert a JSON string to an object.                                      |
| [upload()](expression-functions.md#upload-volume\_ctx)          | Upload a volume to the Neu.ro storage.                                   |
| [parse\_volume()](expression-functions.md#parse\_volume-string) | Parse a volume reference string to an object.                            |
| [hash\_files()](expression-functions.md#hash\_files-pattern)    | Calculate a SHA256 hash of given files.                                  |
| [values()](expression-functions.md#values-dict\_instance)       | Get values from a dictionary.                                            |
| [str()](expression-functions.md#str-any)                        | Convert any object to a string.                                          |
| [replace()](expression-functions.md#replace-string-old-new)     | Replace all occurrences of a symbol sequence in a string with a new one. |
| [join()](expression-functions.md#join-separator-array)          | Concatenate an array of strings by inserting a separator between them    |

### `len(s)`

Return the length of an object (the number of items it contains). The argument may be a string, a list, or a dictionary.

**Example:**

```python
${{ len('fooo') }}
```

### `keys(dictionary)`

Get the list of keys in a dictionary.

**Example:**

```python
${{ keys(env) }}
```

### `lower(string)`

Convert a string to lowercase.

**Example:**

```python
${{ lower('VALue') == 'value' }}
```

### `upper(string)`

Convert a string to uppercase.

**Example:**

```python
${{ upper('valUE') == 'VALUE' }}
```

### `fmt(format_string, arg1, ...)`

Perform a string formatting operation. The `format_string` can contain text or replacement fields delimited by curly braces `{}`. The replacement field will be replaced with other arguments' string values in order they appear in the `format_string`.

**Example:**

```python
${{ fmt("Param test value is: {}", params.test) }}
```

{% hint style="info" %}
This function can be useful in situations when you want to get a value from a mapping using a non-static key:

```python
${{ needs[fmt("{}-{}", matrix.x, matrix.y)] }}
```
{% endhint %}

### `to_json(data)`

Convert any data to a JSON string. The result can be converted back using [`from_json(json_string)`](expression-functions.md#from\_json-json\_string).

**Example:**

```python
${{ to_json(env) }}
```

### `from_json(json_string)`

Parse a JSON string to an object.

**Example:**

```python
${{ from_json('{"array": [1, 2, 3], "value": "value"}').value }}
```

### `upload(volume_ctx)`

Upload the volume to the Neu.ro storage and then return the passed argument back. The argument should contain an entry of the [`volumes` context](workflow-syntax/live-workflow-syntax/live-contexts.md#volumes-context). The function will fail if the [`local` attribute](workflow-syntax/live-workflow-syntax/#volumes-less-than-volume-id-greater-than-local) is not set for the corresponding volume definition in the workflow file.

This function allows to automatically upload a volume before a job runs.

**Example:**

```yaml
volumes:
  data:
    remote: storage:data
    mount: /data
    local: data
jobs:
  volumes:
    - ${{ upload(volumes.data).ref_rw }}
```

### `parse_volume(string)`

Parse a volume reference string into an object that resembles an entry of the [`volumes` context](workflow-syntax/live-workflow-syntax/live-contexts.md#volumes-context). The `id` property will be set to `"<volume>"`, and the `local` property will be set to `None`.

**Example:**

```python
${{ parse_volume("storage:data:/mnt/data:rw").mount == "/mnt/data" }}
```

### `hash_files(pattern, ...)`

Calculate the [SHA256 hash](https://en.wikipedia.org/wiki/SHA-2) of the given files.

File names are relative to the flow's root (`${{ flow.workspace }}`).

Glob patterns are supported:

| Pattern  | Meaning                                                   |
| -------- | --------------------------------------------------------- |
| `*`      | matches everything                                        |
| `?`      | matches any single character                              |
| `[seq]`  | matches any character in _seq_                            |
| `[!seq]` | matches any character not in _seq_                        |
| `**`     | recursively matches this directory and all subdirectories |

The calculated hash contains hashed filenames to generate different results when the files are renamed.

**Example:**

```yaml
${{ hash_files('Dockerfile', 'requiremtnts/*.txt', 'modules/**/*.py') }}
```

### `inspect_job(job_name, [suffix])`

Fetch info about a [job](workflow-syntax/live-workflow-syntax/#jobs-job-id-env) in live mode. The `suffix` argument should be used with [multi jobs](workflow-syntax/live-workflow-syntax/#jobs-less-than-job-id-greater-than-multi). The returned object is a [JobDescription](https://neuro-sdk.readthedocs.io/en/latest/jobs\_reference.html#jobdescription).

**Example:**

```yaml
${{ inspect_job('test_job').http_url }}
```

### `values(dict_instance)`

Get values from a dictionary. This is similar to Python's `dict_instance.values()`.

**Example:**

```yaml
${{ values(dictionary) }}
```

### `str(any)`

Convert any object to a string.

**Example:**

```yaml
${{ str(list_of_values) }}
```

### `replace(string, old, new)`

Replace all occurrences of `old` in `string` with `new`.

**Example:**

```yaml
${{ replace("5tring 5tring 5tring", "5", "S") }}
```

### `join(separator, array)`

Concatenate an array of strings by inserting a separator between them.

**Example:**

```yaml
${{ join(", ", ["1", "2", "3"] }}
```

## Task status check functions

The following functions can be used in the [`tasks.enable`](workflow-syntax/batch-workflow-syntax/#tasks-enable) attribute to conditionally enable task execution.

| Function name                                         | Description                                      |
| ----------------------------------------------------- | ------------------------------------------------ |
| [success()](expression-functions.md#success-task\_id) | `True` if given dependencies succeeded.          |
| [failure()](expression-functions.md#failure-task\_id) | `True` if some of the given dependencies failed. |
| [always()](expression-functions.md#always)            | Mark a task to be always executed.               |

### `success([task_id, ...])`

Returns `True` if all of the specified tasks are completed successfully. If no arguments are provided, checks all tasks form [`tasks.needs`](workflow-syntax/batch-workflow-syntax/#tasks-needs).

**Example:**

```yaml
tasks:
  - enable: ${{ success() }}
```

**Example with arguments:**

```yaml
tasks:
  - id: task_1
  - enable: ${{ success('task_1') }}
```

### `failure([task_id, ...])`

Returns `True` if at least one of the specified tasks failed. If no arguments are provided, checks all tasks form [`tasks.needs`](workflow-syntax/batch-workflow-syntax/#tasks-needs). This function doesn't enable task execution if a dependency is skipped or cancelled.

**Example:**

```yaml
tasks:
  - enable: ${{ failure() }}
```

**Example with arguments:**

```yaml
tasks:
  - id: task_1
  - enable: ${{ failure('task_1') }}
```

### `always()`

Returns a special mark so that Neuro Flow will always run this task, even if some tasks in [`tasks.needs`](workflow-syntax/batch-workflow-syntax/#tasks-needs) have failed or were skipped, or the workflow was [cancelled](cli.md#neuro-flow-cancel).

**Example:**

```yaml
tasks:
  - enable: ${{ always() }}
```
