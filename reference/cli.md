# CLI reference

## apolo-flow

**Usage:**

```bash
apolo-flow [OPTIONS] COMMAND [ARGS]...
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
| [_apolo-flow completion_](cli.md#apolo-flow-completion) | Output shell completion code. |

**Commands:**

| Usage | Description |
| :--- | :--- |
| [_apolo-flow bake_](cli.md#apolo-flow-bake) | Start a batch. |
| [_apolo-flow bakes_](cli.md#apolo-flow-bakes) | List existing bakes. |
| [_apolo-flow build_](cli.md#apolo-flow-build) | Build an image. |
| [_apolo-flow cancel_](cli.md#apolo-flow-cancel) | Cancel a bake. |
| [_apolo-flow clean_](cli.md#apolo-flow-clean) | Clean volume. |
| [_apolo-flow clear-cache_](cli.md#apolo-flow-clear-cache) | Clear cache. |
| [_apolo-flow delete-flow_](cli.md#apolo-flow-delete-flow) | Completely remove flow with all related entities |
| [_apolo-flow download_](cli.md#apolo-flow-download) | Download volume. |
| [_apolo-flow init_](cli.md#apolo-flow-init) | Initialize a flow from a selected template. |
| [_apolo-flow inspect_](cli.md#apolo-flow-inspect) | Inspect a bake. |
| [_apolo-flow kill_](cli.md#apolo-flow-kill) | Kill a job. |
| [_apolo-flow logs_](cli.md#apolo-flow-logs) | Print logs. |
| [_apolo-flow mkvolumes_](cli.md#apolo-flow-mkvolumes) | Create all remote folders for volumes. |
| [_apolo-flow ps_](cli.md#apolo-flow-ps) | List all jobs |
| [_apolo-flow restart_](cli.md#apolo-flow-restart) | Start a batch. |
| [_apolo-flow run_](cli.md#apolo-flow-run) | Run a job. |
| [_apolo-flow show_](cli.md#apolo-flow-show) | Show output of baked task. |
| [_apolo-flow status_](cli.md#apolo-flow-status) | Show job status. |
| [_apolo-flow upload_](cli.md#apolo-flow-upload) | Upload volume. |

### apolo-flow completion

Output shell completion code.

**Usage:**

```bash
apolo-flow completion [OPTIONS] COMMAND [ARGS]...
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

**Commands:**

| Usage | Description |
| :--- | :--- |
| [_apolo-flow completion generate_](cli.md#apolo-flow-completion-generate) | Provide instruction for shell completion generation. |
| [_apolo-flow completion patch_](cli.md#apolo-flow-completion-patch) | Automatically patch shell configuration profile to enable completion |

#### apolo-flow completion generate

Provide instruction for shell completion generation.

**Usage:**

```bash
apolo-flow completion generate [OPTIONS] {bash|zsh}
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

#### apolo-flow completion patch

Automatically patch shell configuration profile to enable completion

**Usage:**

```bash
apolo-flow completion patch [OPTIONS] {bash|zsh}
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### apolo-flow bake

Start a batch.

Run BATCH pipeline remotely on the cluster.

**Usage:**

```bash
apolo-flow bake [OPTIONS] BATCH
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

### apolo-flow bakes

List existing bakes.

**Usage:**

```bash
apolo-flow bakes [OPTIONS]
```

**Options:**

| Name | Description |
| :--- | :--- |
| _-t, --tag TAG_ | Filter out bakes by tag \(multiple option\) |
| _--since DATE\_OR\_TIMEDELTA_ | Show bakes created after a specific date \(including\). Use value of format '1d2h3m4s' to specify moment in past relatively to current time. |
| _--until DATE\_OR\_TIMEDELTA_ | Show bakes created before a specific date \(including\). Use value of format '1d2h3m4s' to specify moment in past relatively to current time. |
| _--recent-first / --recent-last_ | Show newer bakes first or last |
| _--help_ | Show this message and exit. |

### apolo-flow build

Build an image.

Assemble the IMAGE remotely and publish it.

**Usage:**

```bash
apolo-flow build [OPTIONS] IMAGE
```

**Options:**

| Name | Description |
| :--- | :--- |
| _-F, --force-overwrite_ | Build even if the destination image already exists. |
| _--help_ | Show this message and exit. |

### apolo-flow cancel

Cancel a bake.

Cancel a bake execution by stopping all started tasks.

**Usage:**

```bash
apolo-flow cancel [OPTIONS] BAKE
```

**Options:**

| Name | Description |
| :--- | :--- |
| _-a, --attempt INTEGER_ | Attempt number, the last attempt by default |
| _--help_ | Show this message and exit. |

### apolo-flow clean

Clean volume.

Clean remote files on VOLUME, use `clean ALL` for cleaning up all volumes.

**Usage:**

```bash
apolo-flow clean [OPTIONS] VOLUME
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### apolo-flow clear-cache

Clear cache.

Use `apolo-flow clear-cache <BATCH>` for cleaning up the cache for BATCH; Use `apolo-flow clear-cache <BATCH> <TASK_ID>` for cleaning up the cache for TASK_ID in BATCH;

`apolo-flow clear-cache ALL` clears all caches.

**Usage:**

```bash
apolo-flow clear-cache [OPTIONS] BATCH [TASK_ID]
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### apolo-flow delete-flow

Completely remove flow with all related entities

**Usage:**

```bash
apolo-flow delete-flow [OPTIONS] FLOW_IDS...
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### apolo-flow download

Download volume.

Download remote files to local for VOLUME, use `download ALL` for downloading all volumes.

**Usage:**

```bash
apolo-flow download [OPTIONS] VOLUME
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### apolo-flow init

Initialize a flow from a selected template.

Creates required storage as well.

**Usage:**

```bash
apolo-flow init [OPTIONS] [[barebone|default]]
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### apolo-flow inspect

Inspect a bake.

Display a list of started/finished tasks of BAKE\_ID.

**Usage:**

```bash
apolo-flow inspect [OPTIONS] BAKE
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

### apolo-flow kill

Kill a job.

Kill JOB-ID, use `kill ALL` for killing all jobs.

**Usage:**

```bash
apolo-flow kill [OPTIONS] JOB_ID [SUFFIX]
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### apolo-flow logs

Print logs.

Display logs for JOB-ID

**Usage:**

```bash
apolo-flow logs [OPTIONS] JOB_ID [SUFFIX]
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### apolo-flow mkvolumes

Create all remote folders for volumes.

**Usage:**

```bash
apolo-flow mkvolumes [OPTIONS]
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### apolo-flow ps

List all jobs

**Usage:**

```bash
apolo-flow ps [OPTIONS]
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### apolo-flow restart

Start a batch.

Run BATCH pipeline remotely on the cluster.

**Usage:**

```bash
apolo-flow restart [OPTIONS] BAKE
```

**Options:**

| Name | Description |
| :--- | :--- |
| _-a, --attempt INTEGER_ | Attempt number, the last attempt by default |
| _--local-executor_ | Run primary job locally |
| _--from-failed / --no-from-failed_ | Restart from the point of failure |
| _--help_ | Show this message and exit. |

### apolo-flow run

Run a job.

RUN job JOB-ID or ATTACH to it if the job is already running

For multi-jobs an explicit job suffix can be used with explicit job arguments.

**Usage:**

```bash
apolo-flow run [OPTIONS] JOB_ID [ARGS]...
```

**Options:**

| Name | Description |
| :--- | :--- |
| _-s, --suffix TEXT_ | Optional suffix for multi-jobs |
| _-p, --param &lt;TEXT TEXT&gt;..._ | Set params of the batch config |
| _--dry-run_ | Print run command instead of starting job. |
| _--help_ | Show this message and exit. |

### apolo-flow show

Show output of baked task.

Display a logged output of TASK\_ID from BAKE\_ID.

**Usage:**

```bash
apolo-flow show [OPTIONS] BAKE TASK_ID
```

**Options:**

| Name | Description |
| :--- | :--- |
| _-a, --attempt INTEGER_ | Attempt number, the last attempt by default |
| _-r, --raw / -R, --no-raw_ | Raw mode disables the output postprocessing \(the output is processed by default\) |
| _--help_ | Show this message and exit. |

### apolo-flow status

Show job status.

Print status for JOB-ID

**Usage:**

```bash
apolo-flow status [OPTIONS] JOB_ID [SUFFIX]
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

### apolo-flow upload

Upload volume.

Upload local files to remote for VOLUME, use `upload ALL` for uploading all volumes.

**Usage:**

```bash
apolo-flow upload [OPTIONS] VOLUME
```

**Options:**

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |

