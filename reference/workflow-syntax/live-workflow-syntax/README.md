# Live workflow syntax

## _Live_ workflow

The live workflow is always located at the `.apolo/live.yml` or `.apolo/live.yaml` file in the flow's root. The following YAML attributes are supported:

## `kind`

**Required** The workflow _kind_, must be _`live`_ for _live_ workflows.

**Expression contexts:** This attribute cannot contain expressions.

## `id`

**Optional** Identifier of the workflow. By default, the `id` is `live`. It's available as a `${{ flow.flow_id }}` in experssions.

Note: Don't confuse this with `${{ flow.project_id }}`, which is defined in the [project configuration](../project-configuration-syntax.md#id) file.

**Expression contexts:** This attribute only allows expressions that don't access contexts.

## `title`

**Optional** Workflow title, any valid string is allowed. It's accessible via `${{ flow.title }}`. If this is not set manually, the default workflow title `live` will be used.

**Expression contexts:** This attribute only allows expressions that don't access contexts.

## `defaults`

**Optional section** A map of default settings that will apply to all jobs in the workflow. You can override these global default settings for specific jobs.

### `defaults.env`

A mapping of environment variables that will be set in all jobs of the workflow. You can also set environment variables that are only available to specific jobs. For more information, see [`jobs.<job-id>.env`](./#jobs-job-id-env-1).

When two or more environment variables are defined with the same name, `apolo-flow` uses the most specific environment variable. For example, an environment variable defined in a job will override the workflow's default.

**Example**:

```yaml
env:
  SERVER: production
```

This attribute also supports dictionaries as values:

```yaml
env: ${{ {'SERVER': 'production'} }}
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `defaults.life_span`

The default lifespan for jobs ran by the workflow. It can be overridden by [`jobs.<job-id>.life_span`](./#jobs-less-than-job-id-greater-than-life\_span). If not set manually, the default job lifespan is 1 day. The lifespan value can be one of the following:

* A `float` number representing the amount of seconds (`3600` represents an hour)
* A string of the following format: `1d6h15m` (1 day, 6 hours, 15 minutes)

For lifespan-disabling emulation, use an arbitrary large value (e.g. `365d`). Keep in mind that this may be dangerous, as a forgotten job will consume cluster resources.

{% hint style="warning" %}
lifespan shorter than _1 minute_ is forbidden.
{% endhint %}

**Example:**

```yaml
defaults:
  life_span: 14d
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `defaults.preset`

The default preset used by all jobs if not overridden by [`jobs.<job-id>.preset`](./#jobs-less-than-job-id-greater-than-preset). The system-wide default preset is used if both `defaults.preset` and `jobs.<job-id>.preset` are omitted.

**Example:**

```yaml
defaults:
  preset: gpu-small
```

### `defaults.volumes`

Volumes that will be mounted to all jobs by default.

**Example:**

```yaml
defaults:
  volumes:
	- storage:some/dir:/mnt/some/dir
	- storage:some/another/dir:/mnt/some/another/dir
```

Default volumes are not passed to actions.

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `defaults.schedule_timeout`

The default timeout for job scheduling. See [`jobs.<job-id>.schedule_timeout`](./#jobs-less-than-job-id-greater-than-schedule\_timeout) for more information.

The attribute accepts the following values:

* A `float` number representing the amount of seconds (`3600` represents an hour)
* A string of the following format: `1d6h15m45s` (1 day, 6 hours, 15 minutes, 45 seconds)

The cluster-wide timeout is used if both `default.schedule_timeout` and `jobs.<job-id>.schedule_timeout` are omitted.

**Example:**

```yaml
defaults:
  schedule_timeout: 1d  # don't fail until tomorrow
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `defaults.tags`

A list of tags that are added to every job created by the workflow. A specific job's definition can extend this global list by using [`jobs.<job-id>.tags`](./#jobs-less-than-job-id-greater-than-tags).

**Example:**

```yaml
defaults:
  tags: [tag-a, tag-b]
```

This attribute supports lists as values.

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `defaults.workdir`

The default working directory for jobs created by this workflow. See [`jobs.<job-id>.workdir`](./#jobs-less-than-job-id-greater-than-workdir) for more information.

**Example:**

```yaml
defaults:
  workdir: /users/my_user
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

## `images`

**Optional section** A mapping of image definitions used by the _live_ workflow.

`apolo-flow build <image-id>` creates an image from the passed `Dockerfile` and uploads it to the Apolo Registry. The `${{ images.img_id.ref }}` expression can be used for pointing an image from a [`jobs.<job-id>.image`](./#jobs-less-than-job-id-greater-than-image).

{% hint style="info" %}
The `images` section is not required. A job can specify the image name in a plain string without referring to the `${{ images.my_image.ref }}` context.

However, this section exists for convenience: there is no need to repeat yourself if you can just point the image reference everywhere in the YAML.
{% endhint %}

### `images.<image-id>`

The key `image-id` is a string and its value is a map of the job's configuration data. You must replace `<image-id>` with a string that is unique to the `images` object. `<image-id>` must start with a letter and contain only alphanumeric characters or underscore symbols `_`. Dashes `-` are not allowed.

### `images.<image-id>.ref`

**Required** Image _reference_ that can be used in the [`jobs.<job-id>.image`](./#jobs-less-than-job-id-greater-than-image) expression.

**Example of self-hosted image:**

```yaml
images:
  my_image:
	ref: image:my_image:latest
```

You can use the image definition to _address_ images hosted on [_Docker Hub_](https://hub.docker.com/search?q=\&type=image) as an _external_ source (while you can't use `apolo-flow` to build this image). All other attributes except for `ref` don't work for _external_ images.

**Example of external image:**

```yaml
images:
  python:
	ref: python:3.9.0
```

{% hint style="info" %}
Use the embedded [`hash_files()`](../../expression-functions.md#hash\_files-pattern) function to generate the built image's tag based on its content.
{% endhint %}

**Example of auto-calculated stable hash:**

```yaml
images:
  my_image:
	ref: image:my_image:${{ hash_files('Dockerfile', 'requirements/*.txt', 'modules/**/*.py') }}
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `images.<image-id>.context`

**Optional** The Docker _context_ used to build an image, a local path relative to the flow's root folder. The context should contain the `Dockerfile` and any additional files and folders that should be copied to the image.

**Example:**

```yaml
images:
  my_image:
	context: path/to/context
```

{% hint style="info" %}
The flow's root folder is the folder that contains the '.apolo' directory. Its path might be referenced via `${{ flow.workspace }}/`.
{% endhint %}

{% hint style="warning" %}
`apolo-flow` cannot build images without the context.
{% endhint %}

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `images.<image-id>.dockerfile`

**Optional** An docker file name used to build the image. If not set, a `Dockerfile` name will be used by default.

**Example:**

```yaml
images:
  my_image:
	dockerfile: ${{ flow.workspace }}/MyDockerfile
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `images.<image-id>.build_preset`

**Optional** A name of the resource preset used to build the docker image. Consider using it if, for instance, a GPU is required to build dependencies within the image.

**Example:**

```yaml
images:
  my_image:
	build_preset: gpu-small
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `images.<image-id>.build_args`

A list of optional build arguments passed to the image builder. See [Docker documentation](https://docs.docker.com/engine/reference/commandline/build/#set-build-time-variables---build-arg) for details.

**Example:**

```yaml
images:
  my_image:
	build_args:
	- ARG1=val1
	- ARG2=val2
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `images.<image-id>.env`

A mapping of _environment variables_ passed to the image builder.

**Example:**

```yaml
images:
  my_image:
	env:
	  ENV1: val1
	  ENV2: val2
```

This attribute also supports dictionaries as values:

```yaml
images:
  my_image:
	env: ${{ {'ENV1': 'val1', 'ENV2': 'val2'} }}
```

{% hint style="info" %}
You can also map platform secrets as the values of environment variables and later utilize them when building an image.

Let's assume you have a `secret:github_password` which gives you access to a needed private repository. In this case, map it as an environment variable `GH_PASS: secret:github_password` into the builder job and pass it further as `--build-arg GH_PASS=$GH_PASS` while building the container.
{% endhint %}

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `images.<image-id>.volumes`

A list of volume references mounted to the image building process.

**Example:**

```yaml
images:
  my_image:
	volumes:
	- storage:folder1:/mnt/folder1:ro
	- storage:folder2:/mnt/folder2
```

This attribute also supports lists as values:

```yaml
images:
  my_image:
	volumes: ${{ ['storage:folder1:/mnt/folder1:ro', 'storage:folder2:/mnt/folder2:ro'] }}
```

{% hint style="info" %}
You can also map platform secrets as files and later utilize them when building an image.

Let's assume you have a `secret:aws_account_credentials` file which gives you access to an S3 bucket needed during building. In this case, attach it as a volume `- secret:aws_account_credentials:/kaniko_context/aws_account_credentials` into the builder job. A file with credentials will appear in the root of the build context, since the build context is mounted in the `/kaniko_context` folder within the builder job.
{% endhint %}

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

## `volumes`

**Optional section** A mapping of volume definitions available in the _live_ workflow. A volume defines a link between the Apolo storage folder, a remote folder that can be mounted to a _live_ job, and a local folder.

Volumes can be synchronized between local and storage versions with the `apolo-flow upload` and `apolo-flow download` commands and they can be mounted to a job by using the [`jobs.<job-id>.volumes`](./#jobs-less-than-job-id-greater-than-volumes) attribute.

{% hint style="info" %}
The `volumes` section is optional. A job can mount a volume by a direct reference string.

However, this section is very handy to use in a bundle with `run`, `upload`, and `download` commands: define a volume once and refer to it everywhere by name instead of using full definition details.
{% endhint %}

### `volumes.<volume-id>`

The key `volume-id` is a string and its value is a map of the volume's configuration data. You must replace `<volume-id>` with a string that is unique to the `volumes` object. The `<volume-id>` must start with a letter and contain only alphanumeric characters or underscore symbols `_`. Dashes `-` are not allowed.

### `volumes.<volume-id>.remote`

**Required** The volume URI on the [Apolo Storage](https://docs.apolo.us/core/platform-storage/storage) ('storage:path/on/storage') or [Apolo Disk](https://docs.apolo.us/core/platform-storage/disks) ('disk:').

**Example:**

```yaml
volumes:
  folder:
	remote: storage:path/to/folder
```

```yaml
volumes:
  folder1:
	remote: disk:disk-a78c0319-d69b-4fe9-8a2d-fc4a0cdffe04
  folder2:
	remote: disk:named-disk
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `volumes.<volume-id>.mount`

**Required** The mount path inside a job.

**Example:**

```yaml
volumes:
  folder:
	mount: /mnt/folder
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `volumes.<volume-id>.local`

**Optional** Volumes can also be associated with folders on a local machine. A _local_ path should be relative to the flow's root and will be used for uploading/downloading content to the storage.

Volumes without a set `local` attribute cannot be used by the `apolo-flow upload` and `apolo-flow download` commands.

**Example:**

```yaml
volumes:
  folder:
	local: path/to/folder
```

{% hint style="warning" %}
`apolo-flow upload` and `apolo-flow download` will not work for volumes whose remote is the Apolo Disk due to specifics of how disks work.
{% endhint %}

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `volumes.<volume-id>.read_only`

**Optional** The volume is mounted as _read-only_ by default if this attribute is set, _read-write_ mode is used otherwise.

**Example:**

```yaml
volumes:
  folder:
	read_only: true
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

## `jobs`

A _live_ workflow can run jobs by their identifiers using the `apolo-flow run <job-id>` command. Each job runs remotely on the Apolo Platform. Jobs could be defined in two different ways: (1) directly in this file or in a separate file and called as an [`action`](../actions-syntax/).

### `jobs.<job-id>` <a href="#jobs-job-id-env" id="jobs-job-id-env"></a>

Each job must have an associated ID. The key `job-id` is a string and its value is a map of the job's configuration data or action call. You must replace `<job-id>` with a string that is unique to the `jobs` object. The `<job-id>` must start with a letter and contain only alphanumeric characters or underscore symbols `_`. Dash `-` is not allowed.

## Attributes for jobs and action calls

The attributes described in this section can be applied both to plain jobs and action calls. To simplify reading, this section uses the term "job" instead of "job or action call".

### `jobs.<job-id>.params`

Params is a mapping of key-value pairs that have default value and could be overridden from a command line by using `apolo-flow run <job-id> --param name1 val1 --param name2 val2`.

This attribute describes a set of names and default values of parameters accepted by a job.

Parameters can be specified in _short_ and _long_ forms.

The short form is compact, but only allows to specify the parameter's name and default value:

```yaml
jobs:
  my_job:
	params:
	  name1: default1
	  name2: ~   # None by default
	  name3: ""  # Empty string by default
```

The long form also allows to specify parameter descriptions. This can be useful for `apolo-flow run` command introspection, shell autocompletion, and generation of more detailed error messages.

```yaml
jobs:
  my_job:
	params:
	  name1:
		default: default1
		descr: The name1 description
	  name2:
		default: ~
		descr: The name2 description
	  name3:
		default: ""
		descr: The name3 description
```

The parameters can be used in expressions for calculating other job attributes, e.g. [`jobs.<job-id>.cmd`](./#jobs-less-than-job-id-greater-than-cmd).

**Example:**

```yaml
jobs:
  my_job:
	params:
	  folder: "."  # search in current folder by default
	  pattern: "*"  # all files by default
	cmd:
	  find ${{ params.folder }} -name ${{ params.pattern }}
```

**Expression contexts:** This attribute only allows expressions that don't access contexts.

## Attributes for jobs

The attributes described in this section are only applicable to plain jobs that are executed by running docker images on the Apolo platform.

### `jobs.<job-id>.image`

**Required** Each job is executed remotely on the Apolo cluster using a _Docker image_. This image can be hosted on [_Docker Hub_](https://hub.docker.com/search?q=\&type=image) (`python:3.9` or `ubuntu:20.04`) or on the Apolo Registry (`image:my_image:v2.3`). If the image is hosted on the Apolo Registry, the image name must start with the `image:` prefix.

**Example with a constant image string:**

```yaml
jobs:
  my_job:
	image: image:my_image:v2.3
```

You may often want to use the reference to [`images.<image-id>`](./#images-less-than-image-id-greater-than).

**Example with a reference to `images` section:**

```yaml
jobs:
  my_job:
	image: ${{ images.my_image.ref }}
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

### `jobs.<job-id>.cmd`

**Optional** A job executes either a _command_, a _bash_ script, or a _python_ script. The `cmd`, `bash,` and `python` are **mutually exclusive**: only one of the three is allowed at the same time. If none of these three attributes are specified, the [`CMD`](https://docs.docker.com/engine/reference/builder/#cmd) from the [`jobs.<job-id>.image`](./#jobs-less-than-job-id-greater-than-image) is used.

The `cmd` attribute points to the command with optional arguments that is available in the executed [`jobs.<job-id>.image`](./#jobs-less-than-job-id-greater-than-image).

**Example:**

```yaml
jobs:
  my_job:
	cmd: tensorboard --host=0.0.0.0
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

### `jobs.<job-id>.bash`

**Optional** This attribute contains a `bash` script to run.

Using `cmd` to run bash scripts can be tedious: you need to apply quotas to the executed script and set proper bash flags allowing to fail on error.

The `bash` attribute is essentially a shortcut for `cmd: bash -euo pipefail -c <shell_quoted_attr>` .

This form is especially handy for executing complex multi-line bash scripts.

`cmd`, `bash`, and `python` are **mutually exclusive**.

`bash` should be pre-installed on the image to make this attribute work.

**Example:**

```yaml
jobs:
  my_job:
	bash: |
	  for arg in {1..5}
	  do
		echo "Step ${arg}"
		sleep 1
	  done
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

### `jobs.<job-id>.python`

This attribute contains a `python` script to run.

Python is usually considered to be one of the best languages for scientific calculation. If you prefer writing simple inlined commands in `python` instead of `bash`, this notation is great for you.

The `python` attribute is essentially a shortcut for `cmd: python3 -uc <shell_quoted_attr>` .

The `cmd`, `bash`, and `python` are **mutually exclusive**.

`python3` should be pre-installed on the image to make this attribute work.

**Example:**

```yaml
jobs:
  my_job:
	python: |
	  import sys
	  print("The Python version is", sys.version)
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

### `jobs.<job-id>.browse`

**Optional** Open a job's _Http URL_ in a browser after the job startup. `false` by default.

Use this attribute in scenarios like starting a Jupyter Notebook job and opening the notebook session in a browser.

**Example:**

```yaml
jobs:
  my_job:
	browse: true
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

### `jobs.<job-id>.detach`

**Optional** By default, `apolo-flow run <job-id>` keeps the terminal attached to the spawned job. This can help with viewing the job's logs and running commands in its embedded bash session.

Enable the `detach` attribute to disable this behavior.

**Example:**

```yaml
jobs:
  my_job:
	detach: true
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

### `jobs.<job-id>.entrypoint`

**Optional** You can override a Docker image [`ENTRYPOINT`](https://docs.docker.com/engine/reference/builder/#entrypoint) if needed or set it if one wasn't already specified. Unlike the Docker `ENTRYPOINT` instruction which has a shell and exec form, the `entrypoint` attribute only accepts a single string defining an executable to be run.

**Example:**

```yaml
jobs:
  my_job:
	entrypoint: sh -c "Echo $HOME"
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

### `jobs.<job-id>.env` <a href="#jobs-job-id-env" id="jobs-job-id-env"></a>

**Optional** Set environment variables for `<job-id>` to use in the executed job. You can also set environment variables for the entire workflow. For more information, see [`defaults.env`](./#defaults-env).

When two ore more environment variables are defined with the same name, `apolo-flow` uses the most specific environment variable. For example, an environment variable defined in a task will override the [workflow default](./#defaults-env).

**Example:**

```yaml
jobs:
  my_job:
	env:
	  ENV1: val1
	  ENV2: val2
```

This attribute also supports dictionaries as values:

```yaml
jobs:
  my_job:
	env: ${{ {'ENV1': 'val1', 'ENV2': 'val2'} }}
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

### `jobs.<job-id>.http_auth`

**Optional** Control whether the HTTP port exposed by the job requires the Apolo Platform authentication for access.

You may want to disable the authentication to allow everybody to access your job's exposed web resource.

By default, jobs have HTTP protection enabled.

**Example:**

```yaml
jobs:
  my_job:
	http_auth: false
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

### `jobs.<job-id>.http_port`

**Optional** The job's HTTP port number that will be exposed globally on the platform.

By default, the Apolo Platform exposes the job's internal `80` port as an HTTPS-protected resource. This will be listed in the oputput of the `apolo-flow status <job-id>` command as _Http URL_.

You may want to expose a different local port. Use `0` to disable the feature entirely.

**Example:**

```yaml
jobs:
  my_job:
	http_port: 8080
```

{% hint style="warning" %}
Only HTTP traffic is allowed. The platform will automatically encapsulate it into TLS to provide an HTTPS connection.
{% endhint %}

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

### `jobs.<job-id>.life_span`

**Optional** The time period after which a job will be automatically killed.

By default, jobs live 1 day. You may want to change this period by customizing the attribute.

The value could be:

* A float number representing an amount of seconds (`3600` for an hour)
* An expression in the following format: `1d6h15m` (1 day, 6 hours, 15 minutes)

Use an arbitrary large value (e.g. `365d`) for lifespan-disabling emulation. Keep in mind that this can be dangerous, as a forgotten job will consume cluster resources.

The [`defaults.life_span`](./#defaults-life\_span) value is used if the attribute is not set.

**Example:**

```yaml
jobs:
  my_job:
	life_span: 14d12h
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

### `jobs.<job-id>.name`

**Optional** Allows you to specify a job's name. This name becomes a part of the job's internal hostname and exposed HTTP URL, and the job can then be controlled by its name through the low-level `apolo` tool.

The name is completely _optional_.

**Example:**

```yaml
jobs:
  my_job:
	name: my-name
```

If the name is not specified in the `name` attribute, the default name for the job will be automatically generated as follows:

```yaml
'<PROJECT-ID>-<JOB-ID>[-<MULTI_SUFFIX>]'
```

The `[-<MULTI_SUFFIX>]` part makes sure that a job will have a unique name even if it's a multi job.

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

### `jobs.<job-id>.multi`

**Optional** By default, a job can only have one running instance at a time. Calling `apolo-flow run <job-id>` for the same job ID will attach to the already running job instead of creating a new one. This can be overridden by enabling the `multi` attribute.

**Example:**

```yaml
jobs:
  my_job:
	multi: true
```

**Expression contexts:** This attribute only allows expressions that don't access contexts.

### `jobs.<job-id>.pass_config`

**Optional** Set this attribute to `true` if you want to pass the Apolo config used to execute the `apolo-flow run ...` command into the spawned job. This can be useful if you're using a job image with Apolo CLI installed and want to execute `apolo ...` commands _inside_ the running job.

By default, the config is not passed.

**Example:**

```yaml
jobs:
  my_job:
	pass_config: true
```

{% hint style="warning" %}
The lifetime of passed credentials is bound to the job's lifetime. It will be impossible to use them when the job is terminated.
{% endhint %}

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

### `jobs.<job-id>.restart`

**Optional** Control the job behavior when main process exits.

Possible values: `never` (default), `on-failure` and `always`.

Set this attribute to `on-failure` if you want your job to be restarted if the main process exits with non-zero exit code. If you set this attribute to `always,` the job will be restarted even if the main process exits with 0. In this case you will need to terminate the job manually or it will be automatically terminated when it's lifespan ends. `never` implies the platform does not restart the job and this value is used by default.

**Example:**

```yaml
jobs:
  my_job:
	restart: on-failure
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

### `jobs.<job-id>.port-forward`

**Optional** You can define a list of TCP tunnels for the job.

Each port forward entry is a string of a `<LOCAL_PORT>:<REMOTE_PORT>` format.

When the job starts, all enumerated _remote ports_ on the job's side are bound to the developer's box and are available under the corresponding _local port_ numbers.

You can use this feature for remote debugging, accessing a database running in the job, etc.

**Example:**

```yaml
jobs:
  my_job:
	port_forward:
	- 6379:6379  # Default Redis port
	- 9200:9200  # Default Zipkin port
```

This attribute also supports lists as values:

```yaml
jobs:
  my_job:
	port_forward: ${{ ['6379:6379', '9200:9200'] }}
```

### `jobs.<job-id>.preset`

**Optional** The preset to execute the job with. [`defaults.preset`](./#defaults-preset) is used if the preset is not specified for the job.

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

### `jobs.<job-id>.schedule_timeout`

**Optional** Use this attribute if you want to increase the _schedule timeout_. This will prevent a job from failing if the Apolo cluster is under high load and requested resources are likely to not be available at the moment.

If the Apolo cluster has no resources to launch a job immediately, this job is pushed into the waiting queue. If the job is still not started at the end of the _schedule timeout_, it will be failed.

The default system-wide _schedule timeout_ is controlled by the cluster administrator and is usually about 5-10 minutes.

The value of this attribute can be:

* A `float` number representing an amount of seconds
* A string in the following format: `1d6h15m45s` (1 day, 6 hours, 15 minutes, 45 seconds)

See [`defaults.schedule_timeout`](./#defaults-schedule\_timeout) if you want to set a workflow-wide schedule timeout for all jobs.

**Example:**

```yaml
jobs:
  my_job:
	schedule_timeout: 1d  # don't fail until tomorrow
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

### `jobs.<job-id>.tags`

**Optional** A list of additional job tags.

Each _live_ job is tagged. A job's tags are taken from this attribute, [`defaults.tags`](./#defaults-tags), and system tags (`project:<project-id>` and `job:<job-id>`).

**Example:**

```yaml
jobs:
  my_job:
	tags:
	- tag-a
	- tag-b
```

This attribute also supports lists as values:

```yaml
jobs:
  my_job:
	tags: {{ ['tag-a', 'tag-b'] }}
```

### `jobs.<job-id>.title`

**Optional** A job's title. Equal to `<job-id>` by default if not overridden.

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

### `jobs.<job-id>.volumes`

**Optional** A list of job volumes. You can specify a plain string for a volume reference or use the `${{ volumes.<volume-id>.ref }}` expression.

**Example:**

```yaml
jobs:
  my_job:
	volumes:
	- storage:path/to:/mnt/path/to
	- ${{ volumes.my_volume.ref }}
```

This attribute also supports lists as values:

```yaml
jobs:
  my_job:
	volumes: ${{ ['storage:path/to:/mnt/path/to', volumes.my_volume.ref] }}
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

### `jobs.<job-id>.workdir`

**Optional** A working directory to use inside the job.

This attribute takes precedence if specified. Otherwise, [`defaults.workdir`](./#defaults-workdir) takes priority. If none of the previous are specified, a [`WORKDIR`](https://docs.docker.com/engine/reference/builder/#workdir) definition from the image is used.

**Example:**

```yaml
jobs:
  my_job:
	workdir: /users/my_user
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).

## Attributes for actions calls

The attributes described in this section are only applicable to action calls. An action is a reusable part that can be integrated into a workflow. Refer to the [actions reference](../actions-syntax/) to learn more about actions.

### `jobs.<job-id>.action`

**Required** A URL that selects an action to run. It supports two schemes:

* `workspace:` or `ws:` for action files that are stored locally
* `github:` or `gh:` for actions that are bound to a Github repository

The `ws:` scheme expects a valid filesystem path to the action file.

The `gh:` scheme expects the following format: `{owner}/{repo}@{tag}`. Here, `{owner}` is the owner of the Github repository, `{repo}` is the repository's name, and `{tag}` is the commit tag. Commit tags are used to allow versioning of actions.

**Example of the `ws:` scheme**

```yaml
jobs:
  my_job:
	action: ws:path/to/file/some-action.yml
```

**Example of the `gh:` scheme**

```yaml
jobs:
  my_job:
	action: gh:username/repository@v1
```

**Expression contexts:** This attribute only allows expressions that don't access contexts.

### `jobs.<job-id>.args`

**Optional** Mapping of values that will be passed to the actions as arguments. This should correspond to [`inputs`](../actions-syntax/#inputs) defined in the action file. Each value should be a string.

**Example:**

```yaml
jobs:
  my_job:
	args:
	  param1: value1          # You can pass constant
	  param2: ${{ flow.id }}  # Or some expresion value
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) (if [`jobs.<job-id>.multi`](./#jobs-less-than-job-id-greater-than-multi) is set).
