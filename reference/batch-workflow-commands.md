# Batch workflow commands

Tasks executed during _batch_ workflows set some values using commands. To execute a command, a task should print a specifically formatted line to the standard output stream. Neuro Flow automatically scans this stream and detects commands in it.

## `set-output` command

Sets the value of a task's output that can be later accessed by other tasks using the [`needs` context](batch-contexts.md#needs-context).

**Format:**

`::set-output name={name}::{value}`

**Example:**

```
echo "::set-output name=output_name::value of the output_name"
```

## `save-state` command

Saves some value in the `main` task of a [stateful action](./#kind-stateful-actions) that can be later accessed by other `post` using the [`state` context](live-actions-contexts.md#state-context).

**Format:**

`::save-state name={name}::{value}`

**Example:**

```
echo "::save-state name=resource_id::id of some resource"
```

## `stop-commands` command

Temporarily disables the processing of commands until an `::{end_token}::` is found in the output.

**Format:**

`::stop-commands::{end_token}`

**Example:**

```
echo "::stop-commands::this will not appear in the file"
cat some-file.txt
echo "::this will not appear in the file::"
```
