# Expression functions

## Basic functions

All expression \(`${{ <expression }}`\) supports a set of pre-built functions:

| Function name | Description |
| :--- | :--- |
| [len\(\)](expression-functions.md#len-s) | Return the length of an argument. |
| [keys\(\)](expression-functions.md#keys-dictionary) | Return keys of the dictionary. |
| [lower\(\)](expression-functions.md#lower-string) | Convert a string to lowercase. |
| [upper\(\)](expression-functions.md#upper-string) | Convert a string to uppercase. |
| [fmt\(\)](expression-functions.md#fmt-format_string-arg-1) | Do a string formating. |
| [to\_json\(\)](expression-functions.md#to_json-data) | Convert an object to the JSON string. |
| [from\_json\(\)](expression-functions.md#from_json-json_string) | Convert a JSON string to the object. |
| [upload\(\)](expression-functions.md#upload-volume_ctx) | Upload volume to Neu.ro storage. |
| [parse\_volume\(\)](expression-functions.md#parse_volume-string) | Parse volume ref string to the object. |
| [hash\_files\(\)](expression-functions.md#hash_files-pattern) | Calculate SHA256 hash of given files |

### `len(s)`

Return the length \(the number of items\) of an object. The argument may be a string, list, or a dictionary.

**Example:**

```python
${{ len('fooo') }}
```

### `keys(dictionary)`

Get a list of keys in some dictionary.

**Example:**

```python
${{ keys(env) }}
```

### `lower(string)`

Convert string to lowercase.

**Example:**

```python
${{ lower('VALue') == 'value' }}
```

### `upper(string)`

Convert string to uppercase.

**Example:**

```python
${{ upper('valUE') == 'VALUE' }}
```

### `fmt(format_string, arg1, ...)`

Perform a string formatting operation. The `format_string` can contain literal text or replacement fields delimited by braces `{}`. The replacement filed will be replaced with other arguments string values in order as they appear in `format_string`.

**Example:**

```python
${{ fmt("Param test value is: {}", params.test) }}
```

{% hint style="info" %}
This function can be useful in situations where you want to get value from mapping using a non-static key:

```python
${{ needs[fmt("{}-{}", matrix.x, matrix.y)] }}
```
{% endhint %}

### `to_json(data)`

Convert any data to a JSON string. The result can be converted back using [`from_json(json_string)`](expression-functions.md#from_json-json_string).

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

Upload volume to Neu.ro storage and then return passed argument back. The argument should an entry of [`volumes`  context](live-contexts.md#volumes-context). The function will fail if the [`local` attribute](live-workflow-syntax.md#volumes-less-than-volume-id-greater-than-local) is not set for the corresponding volume definition in the workflow file. 

This function allows to automatically upload volume before the job runs.

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

Parse volume ref string into an object that resembles entry of [`volumes`  context](live-contexts.md#volumes-context). The `id` property will be set to `"<volume>"` and the `local` property will be set to `None`.

**Example:**

```python
${{ parse_volume("storage:data:/mnt/data:rw").mount == "/mnt/data" }}
```

### `hash_files(pattern, ...)`

Calculate [the SHA256](https://en.wikipedia.org/wiki/SHA-2) hash of given files.

File names are relative to the project root \(`${{ flow.workspace }}`\).

Glob patterns are supported:

| Pattern | Meaning |
| :--- | :--- |
| `*` | matches everything |
| `?` | matches any single character |
| `[seq]` | matches any character in _seq_ |
| `[!seq]` | matches any character not in _seq_ |
| `**` | matches this directory and all subdirectories, recursively |

The calculated hash contains hashed filenames to generate different results on the bare file renaming.

**Example:**

```yaml
${{ hash_files('Dockerfile', 'requiremtnts/*.txt', 'modules/**/*.py') }}
```

## Task status check functions

The following functions can be used in [`tasks.enable`](batch-workflow-syntax.md#tasks-enable) attribute to conditionally enable task execution.

| Function name | Description |
| :--- | :--- |
| [success\(\)](expression-functions.md#success-task_id) | `True` if given dependencies succeeded |
| [failure\(\)](expression-functions.md#failure-task_id) | `True` if some of the given dependencies failed. |
| [always\(\)](expression-functions.md#always) | Mark task to always execute. |

### `success([task_id, ...])`

Returns `True` if all of the specified tasks are completed successfully. If no arguments provided, checks all tasks form [`tasks.needs`](batch-workflow-syntax.md#tasks-needs).

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

Returns `True` if at least one of the specified tasks has failed. If no arguments provided, checks all tasks form [`tasks.needs`](batch-workflow-syntax.md#tasks-needs). This function does not enable task execution if dependency is skipped or canceled.

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

Returns special mark so that Neuro Flow will always run this task, even if some tasks in [`tasks.needs`](batch-workflow-syntax.md#tasks-needs) have failed or was skipped, or flow execution was [canceled](cli.md#neuro-flow-cancel).

**Example:**

```yaml
tasks:
  - enable: ${{ always() }}
```

