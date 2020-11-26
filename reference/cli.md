

# Table of Contents
* [neuro-flow](#neuro-flow)
	* [neuro-flow completion](#neuro-flow-completion)
		* [neuro-flow completion generate](#neuro-flow-completion-generate)
		* [neuro-flow completion patch](#neuro-flow-completion-patch)
	* [neuro-flow bake](#neuro-flow-bake)
	* [neuro-flow bakes](#neuro-flow-bakes)
	* [neuro-flow build](#neuro-flow-build)
	* [neuro-flow cancel](#neuro-flow-cancel)
	* [neuro-flow clean](#neuro-flow-clean)
	* [neuro-flow clear-cache](#neuro-flow-clear-cache)
	* [neuro-flow download](#neuro-flow-download)
	* [neuro-flow inspect](#neuro-flow-inspect)
	* [neuro-flow kill](#neuro-flow-kill)
	* [neuro-flow logs](#neuro-flow-logs)
	* [neuro-flow mkvolumes](#neuro-flow-mkvolumes)
	* [neuro-flow ps](#neuro-flow-ps)
	* [neuro-flow restart](#neuro-flow-restart)
	* [neuro-flow run](#neuro-flow-run)
	* [neuro-flow show](#neuro-flow-show)
	* [neuro-flow status](#neuro-flow-status)
	* [neuro-flow upload](#neuro-flow-upload)

# neuro-flow

**Usage:**

```bash
neuro-flow [OPTIONS] COMMAND [ARGS]...
```

**Options:**

| Name | Description |
|------|-------------|
| _--config PATH_ | Path to a directory with .neuro folder inside, automatic lookup is performed if not set \(default) |
| _\-v, --verbose_ | Give more output. Option is additive, and can be used up to 2 times. |
| _\-q, --quiet_ | Give less output. Option is additive, and can be used up to 2 times. |
| _\--show-traceback_ | Show python traceback on error, useful for debugging the tool. |
| _--version_ | Show the version and exit. |
| _--help_ | Show this message and exit. |


**Command Groups:**

| Usage | Description |
|-------|-------------|
| _[neuro-flow completion](#neuro-flow-completion)_ | Output shell completion code. |


**Commands:**

| Usage | Description |
|-------|-------------|
| _[neuro-flow bake](#neuro-flow-bake)_ | Start a batch. |
| _[neuro-flow bakes](#neuro-flow-bakes)_ | List existing bakes. |
| _[neuro-flow build](#neuro-flow-build)_ | Build an image. |
| _[neuro-flow cancel](#neuro-flow-cancel)_ | Cancel a bake. |
| _[neuro-flow clean](#neuro-flow-clean)_ | Clean volume. |
| _[neuro\-flow clear-cache](#neuro-flow-clear-cache)_ | Clear cache. |
| _[neuro-flow download](#neuro-flow-download)_ | Download volume. |
| _[neuro-flow inspect](#neuro-flow-inspect)_ | Inspect a bake. |
| _[neuro-flow kill](#neuro-flow-kill)_ | Kill a job. |
| _[neuro-flow logs](#neuro-flow-logs)_ | Print logs. |
| _[neuro-flow mkvolumes](#neuro-flow-mkvolumes)_ | Create all remote folders for volumes. |
| _[neuro-flow ps](#neuro-flow-ps)_ | List all jobs |
| _[neuro-flow restart](#neuro-flow-restart)_ | Start a batch. |
| _[neuro-flow run](#neuro-flow-run)_ | Run a job. |
| _[neuro-flow show](#neuro-flow-show)_ | Show output of baked task. |
| _[neuro-flow status](#neuro-flow-status)_ | Show job status. |
| _[neuro-flow upload](#neuro-flow-upload)_ | Upload volume. |




## neuro-flow completion

Output shell completion code.

**Usage:**

```bash
neuro-flow completion [OPTIONS] COMMAND [ARGS]...
```

**Options:**

| Name | Description |
|------|-------------|
| _--help_ | Show this message and exit. |


**Commands:**

| Usage | Description |
|-------|-------------|
| _[neuro-flow completion generate](#neuro-flow-completion-generate)_ | Provide an instruction for shell completion generation. |
| _[neuro-flow completion patch](#neuro-flow-completion-patch)_ | Automatically patch shell configuration profile to enable completion |




### neuro-flow completion generate

Provide an instruction for shell completion generation.

**Usage:**

```bash
neuro-flow completion generate [OPTIONS] [bash|zsh]
```

**Options:**

| Name | Description |
|------|-------------|
| _--help_ | Show this message and exit. |




### neuro-flow completion patch

Automatically patch shell configuration profile to enable completion

**Usage:**

```bash
neuro-flow completion patch [OPTIONS] [bash|zsh]
```

**Options:**

| Name | Description |
|------|-------------|
| _--help_ | Show this message and exit. |




## neuro-flow bake

Start a batch.<br/><br/>Run BATCH pipeline remotely on the cluster.

**Usage:**

```bash
neuro-flow bake [OPTIONS] BATCH
```

**Options:**

| Name | Description |
|------|-------------|
| _\--local-executor_ | Run primary job locally |
| _--param <TEXT TEXT>..._ | Set params of the batch config |
| _--help_ | Show this message and exit. |




## neuro-flow bakes

List existing bakes.

**Usage:**

```bash
neuro-flow bakes [OPTIONS]
```

**Options:**

| Name | Description |
|------|-------------|
| _--help_ | Show this message and exit. |




## neuro-flow build

Build an image.<br/><br/>Assemble the IMAGE remotely and publish it.

**Usage:**

```bash
neuro-flow build [OPTIONS] IMAGE
```

**Options:**

| Name | Description |
|------|-------------|
| _--help_ | Show this message and exit. |




## neuro-flow cancel

Cancel a bake.<br/><br/>Cancel a bake execution by stopping all started tasks.

**Usage:**

```bash
neuro-flow cancel [OPTIONS] BAKE_ID
```

**Options:**

| Name | Description |
|------|-------------|
| _\-a, --attempt INTEGER_ | Attempt number, the last attempt by default |
| _--help_ | Show this message and exit. |




## neuro-flow clean

Clean volume.<br/><br/>Clean remote files on VOLUME, use `clean ALL` for cleaning up all volumes.

**Usage:**

```bash
neuro-flow clean [OPTIONS] VOLUME
```

**Options:**

| Name | Description |
|------|-------------|
| _--help_ | Show this message and exit. |




## neuro-flow clear-cache

Clear cache.<br/><br/>Use `neuro\-flow clear-cache <BATCH>` for cleaning up the cache for BATCH;<br/><br/>`neuro\-flow clear-cache ALL` clears all caches.

**Usage:**

```bash
neuro-flow clear-cache [OPTIONS] BATCH
```

**Options:**

| Name | Description |
|------|-------------|
| _--help_ | Show this message and exit. |




## neuro-flow download

Download volume.<br/><br/>Download remote files to local for VOLUME, use `download ALL` for<br/>downloading all volumes.

**Usage:**

```bash
neuro-flow download [OPTIONS] VOLUME
```

**Options:**

| Name | Description |
|------|-------------|
| _--help_ | Show this message and exit. |




## neuro-flow inspect

Inspect a bake.<br/><br/>Display a list of started/finished tasks of BAKE_ID.

**Usage:**

```bash
neuro-flow inspect [OPTIONS] BAKE_ID
```

**Options:**

| Name | Description |
|------|-------------|
| _\-a, --attempt INTEGER_ | Attempt number, the last attempt by default |
| _\-o, --output-graph FILE_ | A path to Graphviz \(DOT) file. Autogenerated from BAKE_ID and attempt number by default |
| _--dot_ | Save DOT file with tasks statuses. |
| _--pdf_ | Save PDF file with tasks statuses. |
| _--view_ | Open generated PDF file with tasks statuses. |
| _--help_ | Show this message and exit. |




## neuro-flow kill

Kill a job.<br/><br/>Kill JOB-ID, use `kill ALL` for killing all jobs.

**Usage:**

```bash
neuro-flow kill [OPTIONS] JOB_ID [SUFFIX]
```

**Options:**

| Name | Description |
|------|-------------|
| _--help_ | Show this message and exit. |




## neuro-flow logs

Print logs.<br/><br/>Display logs for JOB-ID

**Usage:**

```bash
neuro-flow logs [OPTIONS] JOB_ID [SUFFIX]
```

**Options:**

| Name | Description |
|------|-------------|
| _--help_ | Show this message and exit. |




## neuro-flow mkvolumes

Create all remote folders for volumes.

**Usage:**

```bash
neuro-flow mkvolumes [OPTIONS]
```

**Options:**

| Name | Description |
|------|-------------|
| _--help_ | Show this message and exit. |




## neuro-flow ps

List all jobs

**Usage:**

```bash
neuro-flow ps [OPTIONS]
```

**Options:**

| Name | Description |
|------|-------------|
| _--help_ | Show this message and exit. |




## neuro-flow restart

Start a batch.<br/><br/>Run BATCH pipeline remotely on the cluster.

**Usage:**

```bash
neuro-flow restart [OPTIONS] BAKE_ID
```

**Options:**

| Name | Description |
|------|-------------|
| _\-a, --attempt INTEGER_ | Attempt number, the last attempt by default |
| _\--local-executor_ | Run primary job locally |
| _\--from-failed / --no-from-failed_ | Restart from the point of failure |
| _--help_ | Show this message and exit. |




## neuro-flow run

Run a job.<br/><br/>RUN job JOB-ID or ATTACH to it if the job is already running<br/><br/>For multi-jobs an explicit job suffix can be used with explicit job<br/>arguments.

**Usage:**

```bash
neuro-flow run [OPTIONS] JOB_ID [ARGS]...
```

**Options:**

| Name | Description |
|------|-------------|
| _\-s, --suffix TEXT_ | Optional suffix for multi-jobs |
| _--param <TEXT TEXT>..._ | Set params of the batch config |
| _--help_ | Show this message and exit. |




## neuro-flow show

Show output of baked task.<br/><br/>Display a logged output of TASK\_ID from BAKE_ID.

**Usage:**

```bash
neuro-flow show [OPTIONS] BAKE_ID TASK_ID
```

**Options:**

| Name | Description |
|------|-------------|
| _\-a, --attempt INTEGER_ | Attempt number, the last attempt by default |
| _\-r, --raw / -R, --no-raw_ | Raw mode disables the output postprocessing \(the output is processed by default) |
| _--help_ | Show this message and exit. |




## neuro-flow status

Show job status.<br/><br/>Print status for JOB-ID

**Usage:**

```bash
neuro-flow status [OPTIONS] JOB_ID [SUFFIX]
```

**Options:**

| Name | Description |
|------|-------------|
| _--help_ | Show this message and exit. |




## neuro-flow upload

Upload volume.<br/><br/>Upload local files to remote for VOLUME, use `upload ALL` for uploading all<br/>volumes.

**Usage:**

```bash
neuro-flow upload [OPTIONS] VOLUME
```

**Options:**

| Name | Description |
|------|-------------|
| _--help_ | Show this message and exit. |


