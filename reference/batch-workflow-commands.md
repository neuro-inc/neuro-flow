# Batch workflow commands

Tasks executed during the _batch_ workflow set some values using commands. To execute a command, a task should print a specially formatted line to standard output stream. Neuro Flow automatically scans this stream and detects commands.

## `set-output` command

Sets the value of tasks output that can be later accessed by other tasks using [`needs` context](batch-contexts.md#needs-context).

**Format:**

`::set-output name={name}::{value}`

**Example:**

```text
echo "::set-output name=output_name::value of the output_name"
```

## `save-state` command

Save some value in the `main` task of a [stateful action](actions-syntax.md#kind-stateful-actions) that can be later accessed by other `post` using [`state` context](live-actions-contexts.md#state-context).

**Format:**

`::save-state name={name}::{value}`

**Example:**

```text
echo "::save-state name=resource_id::id of some resource"
```

## `stop-commands` command

Temporarily disables processing of commands until `::{end_token}::` appears in the output.

**Format:**

`::stop-commands::{end_token}`

**Example:**

```text
echo "::stop-commands::this will not appear in file"
cat some-file.txt
echo "::this will not appear in file::"
```

