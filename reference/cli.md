# CLI reference

## neuro-flow

**Usage:**

```bash
neuro-flow [OPTIONS] COMMAND [ARGS]...
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--config PATH_ | Path to a directory with .neuro folder inside, automatic lookup is performed if not set \(default\) |
| _-v, --verbose_ | Give more output. Option is additive, and can be used up to 2 times. |
| _-q, --quiet_ | Give less output. Option is additive, and can be used up to 2 times. |
| _--show-traceback_ | Show python traceback on error, useful for debugging the tool. |
| _--version_ | Show the version and exit. |
| _--help_ | Show this message and exit. |

**Command Groups:**

| Usage | Description |
| :--- | :--- |
| [_neuro-flow completion_](cli.md#neuro-flow-completion) | Output shell completion code. |
| [_neuro-flow project_](cli.md#neuro-flow-project) | Project-related commands |

**Commands:**

| Usage | Description |
| :--- | :--- |
| [_neuro-flow bake_](cli.md#neuro-flow-bake) | Start a batch. |
| [_neuro-flow bakes_](cli.md#neuro-flow-bakes) | List existing bakes. |
| [_neuro-flow build_](cli.md#neuro-flow-build) | Build an image. |
| [_neuro-flow cancel_](cli.md#neuro-flow-cancel) | Cancel a bake. |
| [_neuro-flow clean_](cli.md#neuro-flow-clean) | Clean volume. |
| [_neuro-flow clear-cache_](cli.md#neuro-flow-clear-cache) | Clear cache. |
| [_neuro-flow delete-project_](cli.md#neuro-flow-delete-project) | Completely remove project with all related entities |
| [_neuro-flow download_](cli.md#neuro-flow-download) | Download volume. |
| [_neuro-flow inspect_](cli.md#neuro-flow-inspect) | Inspect a bake. |
| [_neuro-flow kill_](cli.md#neuro-flow-kill) | Kill a job. |
| [_neuro-flow logs_](cli.md#neuro-flow-logs) | Print logs. |
| [_neuro-flow mkvolumes_](cli.md#neuro-flow-mkvolumes) | Create all remote folders for volumes. |
| [_neuro-flow ps_](cli.md#neuro-flow-ps) | List all jobs |
| [_neuro-flow restart_](cli.md#neuro-flow-restart) | Start a batch. |
| [_neuro-flow run_](cli.md#neuro-flow-run) | Run a job. |
| [_neuro-flow show_](cli.md#neuro-flow-show) | Show output of baked task. |
| [_neuro-flow status_](cli.md#neuro-flow-status) | Show job status. |
| [_neuro-flow upload_](cli.md#neuro-flow-upload) | Upload volume. |

### neuro-flow completion

Output shell completion code.

**Usage:**

```bash
neuro-flow completion [OPTIONS] COMMAND [ARGS]...
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

**Commands:**

| Usage | Description |
| :--- | :--- |
| [_neuro-flow completion generate_](cli.md#neuro-flow-completion-generate) | Provide instruction for shell completion generation. |
| [_neuro-flow completion patch_](cli.md#neuro-flow-completion-patch) | Automatically patch shell configuration profile to enable completion |

#### neuro-flow completion generate

Provide instruction for shell completion generation.

**Usage:**

```bash
neuro-flow completion generate [OPTIONS] {bash|zsh}
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

#### neuro-flow completion patch

Automatically patch shell configuration profile to enable completion

**Usage:**

```bash
neuro-flow completion patch [OPTIONS] {bash|zsh}
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### neuro-flow project

Project-related commands

**Usage:**

```bash
neuro-flow project [OPTIONS] COMMAND [ARGS]...
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

**Commands:**

| Usage | Description |
| :--- | :--- |
| [_neuro-flow project init_](cli.md#neuro-flow-project-init) | Initialize a project from a selected template |
| [_neuro-flow project template_](cli.md#neuro-flow-project-template) | Provide instructions for the project template usage. |

#### neuro-flow project init

Initialize a project from a selected template

Creates required storage as well

**Usage:**

```bash
neuro-flow project init [OPTIONS] {recommended|barebone}
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

#### neuro-flow project template

Provide instructions for the project template usage.

**Usage:**

```bash
neuro-flow project template [OPTIONS] {recommended|barebone}
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### neuro-flow bake

Start a batch.

Run BATCH pipeline remotely on the cluster.

**Usage:**

```bash
neuro-flow bake [OPTIONS] BATCH
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--local-executor_ | Run primary job locally |
| _-p, --param &lt;TEXT TEXT&gt;..._ | Set params of the batch config |
| _-n, --name NAME_ | Optional bake name |
| _--meta-from-file FILE_ | File with params for batch. |
| _-t, --tag TAG_ | Optional bake tag, multiple values allowed |
| _--help_ | Show this message and exit. |

### neuro-flow bakes

List existing bakes.

**Usage:**

```bash
neuro-flow bakes [OPTIONS]
```

**Options:**

| Name | Description |
| :--- | :--- |
| _-t, --tag TAG_ | Filter out bakes by tag \(multiple option\) |
| _--since DATE\_OR\_TIMEDELTA_ | Show bakes created after a specific date \(including\). Use value of format '1d2h3m4s' to specify moment in past relatively to current time. |
| _--until DATE\_OR\_TIMEDELTA_ | Show bakes created before a specific date \(including\). Use value of format '1d2h3m4s' to specify moment in past relatively to current time. |
| _--recent-first / --recent-last_ | Show newer bakes first or last |
| _--help_ | Show this message and exit. |

### neuro-flow build

Build an image.

Assemble the IMAGE remotely and publish it.

**Usage:**

```bash
neuro-flow build [OPTIONS] IMAGE
```

**Options:**

| Name | Description |
| :--- | :--- |
| _-F, --force-overwrite_ | Build even if the destination image already exists. |
| _--help_ | Show this message and exit. |

### neuro-flow cancel

Cancel a bake.

Cancel a bake execution by stopping all started tasks.

**Usage:**

```bash
neuro-flow cancel [OPTIONS] BAKE
```

**Options:**

| Name | Description |
| :--- | :--- |
| _-a, --attempt INTEGER_ | Attempt number, the last attempt by default |
| _--help_ | Show this message and exit. |

### neuro-flow clean

Clean volume.

Clean remote files on VOLUME, use `clean ALL` for cleaning up all volumes.

**Usage:**

```bash
neuro-flow clean [OPTIONS] VOLUME
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### neuro-flow clear-cache

Clear cache.

Use `neuro-flow clear-cache <BATCH>` for cleaning up the cache for BATCH; Use `neuro-flow clear-cache <BATCH> <TASK_ID>` for cleaning up the cache for TASK_ID in BATCH;

`neuro-flow clear-cache ALL` clears all caches.

**Usage:**

```bash
neuro-flow clear-cache [OPTIONS] BATCH [TASK_ID]
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### neuro-flow delete-project

Completely remove project with all related entities

**Usage:**

```bash
neuro-flow delete-project [OPTIONS] PROJECT_IDS...
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### neuro-flow download

Download volume.

Download remote files to local for VOLUME, use `download ALL` for downloading all volumes.

**Usage:**

```bash
neuro-flow download [OPTIONS] VOLUME
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### neuro-flow inspect

Inspect a bake.

Display a list of started/finished tasks of BAKE\_ID.

**Usage:**

```bash
neuro-flow inspect [OPTIONS] BAKE
```

**Options:**

| Name | Description |
| :--- | :--- |
| _-a, --attempt INTEGER_ | Attempt number, the last attempt by default |
| _-o, --output-graph FILE_ | A path to Graphviz \(DOT\) file. Autogenerated from BAKE\_ID and attempt number by default |
| _--dot_ | Save DOT file with tasks statuses. |
| _--pdf_ | Save PDF file with tasks statuses. |
| _--view_ | Open generated PDF file with tasks statuses. |
| _--help_ | Show this message and exit. |

### neuro-flow kill

Kill a job.

Kill JOB-ID, use `kill ALL` for killing all jobs.

**Usage:**

```bash
neuro-flow kill [OPTIONS] JOB_ID [SUFFIX]
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### neuro-flow logs

Print logs.

Display logs for JOB-ID

**Usage:**

```bash
neuro-flow logs [OPTIONS] JOB_ID [SUFFIX]
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### neuro-flow mkvolumes

Create all remote folders for volumes.

**Usage:**

```bash
neuro-flow mkvolumes [OPTIONS]
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### neuro-flow ps

List all jobs

**Usage:**

```bash
neuro-flow ps [OPTIONS]
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### neuro-flow restart

Start a batch.

Run BATCH pipeline remotely on the cluster.

**Usage:**

```bash
neuro-flow restart [OPTIONS] BAKE
```

**Options:**

| Name | Description |
| :--- | :--- |
| _-a, --attempt INTEGER_ | Attempt number, the last attempt by default |
| _--local-executor_ | Run primary job locally |
| _--from-failed / --no-from-failed_ | Restart from the point of failure |
| _--help_ | Show this message and exit. |

### neuro-flow run

Run a job.

RUN job JOB-ID or ATTACH to it if the job is already running

For multi-jobs an explicit job suffix can be used with explicit job arguments.

**Usage:**

```bash
neuro-flow run [OPTIONS] JOB_ID [ARGS]...
```

**Options:**

| Name | Description |
| :--- | :--- |
| _-s, --suffix TEXT_ | Optional suffix for multi-jobs |
| _-p, --param &lt;TEXT TEXT&gt;..._ | Set params of the batch config |
| _--dry-run_ | Print run command instead of starting job. |
| _--help_ | Show this message and exit. |

### neuro-flow show

Show output of baked task.

Display a logged output of TASK\_ID from BAKE\_ID.

**Usage:**

```bash
neuro-flow show [OPTIONS] BAKE TASK_ID
```

**Options:**

| Name | Description |
| :--- | :--- |
| _-a, --attempt INTEGER_ | Attempt number, the last attempt by default |
| _-r, --raw / -R, --no-raw_ | Raw mode disables the output postprocessing \(the output is processed by default\) |
| _--help_ | Show this message and exit. |

### neuro-flow status

Show job status.

Print status for JOB-ID

**Usage:**

```bash
neuro-flow status [OPTIONS] JOB_ID [SUFFIX]
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### neuro-flow upload

Upload volume.

Upload local files to remote for VOLUME, use `upload ALL` for uploading all volumes.

**Usage:**

```bash
neuro-flow upload [OPTIONS] VOLUME
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

