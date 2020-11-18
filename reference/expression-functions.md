# Expression functions

The expression \(`${{ <expression }}`\) supports a set of pre-built functions:

| Function name | Description |
| :--- | :--- |
| hash\_files\(\) | Calculate SHA256 hash of given files |
|  |  |
|  |  |

### `hash_files(pattern, ...)`

Calculate SHA256 hash of given files.

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



