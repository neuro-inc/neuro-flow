[comment]: # (Please do not modify this file)
[comment]: # (Put you comments to changelog.d and it will be moved to changelog in next release)

[comment]: # (Clear the text on make release for canceling the release)

[comment]: # (towncrier release notes start)

# Neuro Flow 23.10.0 (2023-10-15)

### Features

- Expose jobs and tasks restart policy configuration ([#1072](https://github.com/neuro-inc/neuro-flow/issues/1072))


# Neuro Flow 23.7.0 (2023-07-07)

### Features

- Dropped Python 3.7, added 3.10, 3.11 support. ([#980](https://github.com/neuro-inc/neuro-flow/issues/980))
- Host neuro-flow flows (former projects) within user projects. ([#1002](https://github.com/neuro-inc/neuro-flow/issues/1002))

### Misc

- [#996](https://github.com/neuro-inc/neuro-flow/issues/996), [#1002](https://github.com/neuro-inc/neuro-flow/issues/1002)


# Neuro Flow 22.8.1 (2022-08-05)
==============================

Features
--------

- Added `hash_files_relative` function to expression, it works same as `hash_files` but requires additional leading
  parameters that defines directory to glob over. It can be used to glob over action files:
  ```
    ${{ hash_files_relative(flow.action_path, "**/pattern/here/**/*.py", "other/**/pattern")
  ``` ([#904](https://github.com/neuro-inc/neuro-flow/issues/904))


Neuro Flow 22.8.0 (2022-08-04)
==============================

Features
--------

- Added support of `flow.action_path` for images sections of action. ([#902](https://github.com/neuro-inc/neuro-flow/issues/902))


Neuro Flow 22.7.2 (2022-07-28)
==============================

Features
--------

- Implement `flow.action_path` property in the flow context.  It is available from action and points to the folder where `action.yml` file is located. ([#896](https://github.com/neuro-inc/neuro-flow/issues/896))
- Replace HTTP fetch with git clone for remote actions. ([#897](https://github.com/neuro-inc/neuro-flow/issues/897))


Neuro Flow 22.7.1 (2022-07-25)
==============================

Bugfixes
--------

- Use a separate src folder to don install tests when installing neuro-flow. ([#891](https://github.com/neuro-inc/neuro-flow/issues/891))


Neuro Flow 22.7.0 (2022-07-25)
==============================

Features
--------

- Implement `neuro-flow init` command for easy flow creation ([#859](https://github.com/neuro-inc/neuro-flow/issues/859))


Neuro Flow 22.6.0 (2022-06-07)
==============================

Features
--------

- Add support of shared server side projects. ([#840](https://github.com/neuro-inc/neuro-flow/issues/840))
- Display times with timezones in log messages. ([#847](https://github.com/neuro-inc/neuro-flow/issues/847))


Neuro Flow 22.4.3 (2022-04-21)
==============================

Bugfixes
--------

- Fixed error when trying to build image in batch mode ([#818](https://github.com/neuro-inc/neuro-flow/issues/818))


Neuro Flow 22.4.2 (2022-04-01)
==============================

No significant changes.


Neuro Flow 22.3.0 (2022-03-29)
==============================

Bugfixes
--------

- Fixed problem with click 8.1.0

Neuro Flow 22.1.0 (2022-01-26)
==============================

Features
--------

- Support ${{ matrix.ORDINAL }} as unique 0-based index for selected rows.

  If a batch flow has a matrix, all matrix rows are enumerated.
  The ordinal number of each row is available as `${{ matrix.ORDINAL }}` system value. ([#693](https://github.com/neuro-inc/neuro-flow/issues/693))
- Add support of expressions in matrix definition.

  You can now use expression to define list of matrix products. In examples here and below,
  both `old_way_key` and `new_way_key` produce same list of values:

  ```
  matrix:
    old_way_key: ["1", "2", "3"]
    new_way_key: ${{ ["1", "2", "3"] }}
  ```

  This can be helpful when used together with new `range()` function:

  ```
  matrix:
    old_way_key: [0, 1, 2, 3]
    new_way_key: ${{ range(4) }}
  ```

  The `range()` function supports same parameters as python's `range()`, but it returns list.
  For example: `${{ range(1, 4) }}` generates `[1,2,3]`, and `${{ range(4, 1, -1) }}` generates
  `[4,3,2]`.

  As sometimes plain numbers is not best options for matrix products, you can use list comprehension
  to perform some mapping:

  ```
  matrix:
    old_way_key: ["k1", "k2", "k3"]
    new_way_key: ${{ [fmt("k{}", str(it)) for it in range(1, 4)] }}
  ```

  You can also filter some values in comprehension same way as in python:

  ```
  matrix:
    old_way_key: [0, 4, 16]
    new_way_key: ${{ [it * it for it in range(1, 5) if it % 2 == 0] }}
  ``` ([#741](https://github.com/neuro-inc/neuro-flow/issues/741))


Bugfixes
--------

- Fixed (disabled) uploads to storage in dry-run mode ([#732](https://github.com/neuro-inc/neuro-flow/issues/732))


Neuro Flow 21.11.2 (2021-11-26)
===============================

Features
--------

- Technical release, compatible with the latest SDK/CLI.


Neuro Flow 21.11.0 (2021-11-23)
===============================

Features
--------

- Allow `bash` and `python` code blocks in local actions. ([#667](https://github.com/neuro-inc/neuro-flow/issues/667))
- Add `-s/--suffix` option usage hint for cases when the live job launched without it. ([#679](https://github.com/neuro-inc/neuro-flow/issues/679))


Bugfixes
--------

- Handle cached image status color in `neuro-flow inspect <bake>`. ([#657](https://github.com/neuro-inc/neuro-flow/issues/657))
- Fixed parsing of bash and python in mixins ([#674](https://github.com/neuro-inc/neuro-flow/issues/674))
- Fix parsing of 'bash' and 'python' usage in project config. ([#678](https://github.com/neuro-inc/neuro-flow/issues/678))
- Fixed logging of filename as "." for github actions. ([#681](https://github.com/neuro-inc/neuro-flow/issues/681))


Neuro Flow 21.10.0 (2021-10-27)
===============================

Features
--------

- Added new context called git. It has following attributes:

  - ${{ git.sha }} -- SHA of current commit
  - ${{ git.branch }} - name of current branch
  - ${{ git.tags }} - list of tags that point to current commit

  This context is available everywhere both in live and batch mode, but it can only be used
  if project's workspace is inside some git repository. ([#603](https://github.com/neuro-inc/neuro-flow/issues/603))
- Added ternary operator to expressions: `${{ left if condition else right }}` will evaluate to `left`
  if `condition` is True and to `right` otherwise. ([#605](https://github.com/neuro-inc/neuro-flow/issues/605))
- Allowed ']]' and '}}' in yaml literal strings. ([#607](https://github.com/neuro-inc/neuro-flow/issues/607))
- Added column with batch name to output of `neuro-flow bakes`. ([#618](https://github.com/neuro-inc/neuro-flow/issues/618))
- Enabled detailed automatic logging to file. For locally executed commands, logs will
  go to `~/.neuro/logs` directory. Remote executor detailed logs will go to `storage:.flow/logs/<bake_id>/`. ([#622](https://github.com/neuro-inc/neuro-flow/issues/622))
- Added support of non-string types for action inputs. Now, one can specify action input in following way:

  ```
  inputs:
	arg1:
	  descr: Input with implicit string type
	arg2:
	  descr: Input with explicit string type
	  type: str
	arg2:
	  descr: Input with explicit int type and corresponding default
	  type: int
	  default: 42
  ```

  Supported types are `int`, `float`, `bool`, `str`. On action calls side, it's now possible to use
  corresponding yaml types as arguments. ([#626](https://github.com/neuro-inc/neuro-flow/issues/626))
- Added possibility to specify job/bake params via the shortcut `-p` for `--param`. ([#629](https://github.com/neuro-inc/neuro-flow/issues/629))


Neuro Flow 21.9 (2021-09-29)
==============================

Features
--------

- Renamed `inherits` yaml property to `mixins`. ([#560](https://github.com/neuro-inc/neuro-flow/issues/560))
- Added support project level `mixins`. Mixins defined in `project.yml` available both for live and batch configurations,
  so they cannot define any live or batch specific properties. ([#562](https://github.com/neuro-inc/neuro-flow/issues/562))
- Added command `neuro-flow delete-project <project-id>` that allows complete removal of project. ([#581](https://github.com/neuro-inc/neuro-flow/issues/581))


Bugfixes
--------

- Fix crash with global images in batch mode. ([#544](https://github.com/neuro-inc/neuro-flow/issues/544))


Misc
----

- [#580](https://github.com/neuro-inc/neuro-flow/issues/580)


Neuro Flow 21.7.9 (2021-07-09)
==============================

Features
--------

- Added new sections `defaults`, `images`, `volumes` to the `project.yml` file. The work the same as the do in `live`/`batch` except they are global -- everything defined in `project.yml` applies to all workflows. (#506)


Neuro Flow 21.7.7 (2021-7-7)
============================

Features
--------


- Added modules feature: a module is simillar to action but has following differneces:
  - only local files support (`ws:` scheme), github located modules are forbidden.
  - the module content has access to workflow global defaults. The default env/volumes/preset
  is inherited, and expressions can access top level contexts such as `flow`.

  Calling a module is similar to calling an action, except for use of `module` property
  instead of `action` property:

  Live module call:
  ```
  jobs:
	test:
	  module: ws:live-module
	  args:
		arg1: val 1
  ```

  Batch module call:
  ```
  tasks:
	- id: test
	  module: ws:batch-module
	  args:
		arg1: val 1
  ``` ([#464](https://github.com/neuro-inc/neuro-flow/issues/464))

- Add support of mixins in live and batch mode.

  Mixins allow to define and reuse some common parts of jobs in live mode and tasks in batch mode.
  To define a mixin, use top level `mixins` sections:
  ```
  ...
  mixins:
	credentials:
	  volumes:
		- secret:some_key:/var/some_key
	  env:
		KEY_LOCATION: /var/some_key
  ...
  ```

  Mixins can define the same properties as "job" and "task" do, except for "id" field in batch mode.
  To apply a mixin, use `inherits` property:

  ```
  ...
  jobs:
	test_a:
	  inherits: [ credentials ]
  ...
  ```

  When applied, all fields defined in mixin will be merged into job definition.
  You can apply multiple mixins simultaneously. If some of applied mixins share the same property,
  or/and it is defined in task, the following rules are applied:
  - If property is scalar (int/string/bool), then job will use value defined in job definition. If it is absent,
  the value from the rightmost of the mixins that define this property will be used:
  ```
  mixins:
	mix1:
	  image: example_mix1
	mix2:
	  image: example_mix2
  jobs:
	job1:
	  inherits: [mix1, mix2]
	  image: example
	job2:
	  inherits: [mix1, mix2]
  ```
  The `job1` will use `example` image, and `job2` will use `example_mix2` image.
  - If property is list, that all lists will be concatenated.
  - If property is dict, that rule for scalars will be applied for dict values separately.

  Mixins can inherit from each other:
  ```
  mixins:
	mix1:
	  env:
		TEST: 1
	mix2:
	  inherits: [ mix1 ]
	  image: example
  ``` ([#498](https://github.com/neuro-inc/neuro-flow/issues/498))


Bugfixes
--------


- Improved performance of `neuro flow bakes` it will now print only new rows instead of re-rendering all table ([#501](https://github.com/neuro-inc/neuro-flow/issues/501))


Neuro Flow 21.6.23 (2021-6-23)
==============================

Features
--------


- Implement retry on NDJSON errors ([#493](https://github.com/neuro-inc/neuro-flow/issues/493))


Neuro Flow 21.6.18.1 (2021-6-18)
================================

Bugfixes
--------


- Fix cache key calculation: now it doesn't depend on top-level contexts but on a task calculated parameters plus "needs" and "state" for stateful actions only.


Neuro Flow 21.6.18 (2021-6-18)
==============================

Bugfixes
--------


- Fix READ retry logic: increase delay between retries (was decreasing to zero in
  21.6.17 release by mistake).


Neuro Flow 21.6.17 (2021-6-17)
==============================

Features
--------


- Added command to clear cache of a single task: `neuro-flow clear-cache <batch> <task_id>`. ([#452](https://github.com/neuro-inc/neuro-flow/issues/452))

- Added support in live jobs params. The following contexts are now available under `jobs.<job-id>.params`:
  `project`, `flow`, `env`, `tags`, `volumes`, `images`. ([#457](https://github.com/neuro-inc/neuro-flow/issues/457))

- Generate default live job name as '<PROJECT-ID>-<JOB-ID>-[<MULTI_SUFFIX>]' if not set. ([#462](https://github.com/neuro-inc/neuro-flow/issues/462))

- Retry operations inside a batch runner if possible; it increase baking stability. ([#483](https://github.com/neuro-inc/neuro-flow/issues/483))


Bugfixes
--------


- Fixed bug when executor ignored bake cancellation. ([#449](https://github.com/neuro-inc/neuro-flow/issues/449))

- Fixed wrong filename of action config file in logs. ([#450](https://github.com/neuro-inc/neuro-flow/issues/450))

- Fixed missing id of initial job for cached tasks. ([#451](https://github.com/neuro-inc/neuro-flow/issues/451))

- Don't attach to live job in dry-run mode. ([#463](https://github.com/neuro-inc/neuro-flow/issues/463))


Neuro Flow 21.6.2 (2021-6-2)
============================

Bugfixes
--------


- Fixed hanging when executor tried to build an image in batch mode. ([#448](https://github.com/neuro-inc/neuro-flow/issues/448))


Neuro Flow 21.5.31 (2021-05-31)
===============================

Bugfixes
--------


- Fix broken cache when using images: now remote context dir name is based on image ref instead of random name. ([#422](https://github.com/neuro-inc/neuro-flow/issues/422))

- Fix a error that leads to bakes cache check miss even if the record is present in cache actually. ([#441](https://github.com/neuro-inc/neuro-flow/issues/441))


Neuro Flow 21.5.25 (2021-05-25)
===============================


Features
--------


- Support shared projects. Shared project should have parameters `owner` or `role` set in `project.yml`. ([#373](https://github.com/neuro-inc/neuro-flow/issues/373))

- Add bake id to `neuro-flow inspect`. ([#396](https://github.com/neuro-inc/neuro-flow/issues/396))

- Added support of `storage:` urls in `images.<image-id>.context` and `images.<image-id>.dockerfile`. ([#402](https://github.com/neuro-inc/neuro-flow/issues/402))

- Added image building functionality to batch mode.
  The `images` yaml section entries with `context` and `dockerfile` are now allowed
  both in batch and batch action config files.
  Image build starts automatically when task that uses it is ready to be run. ([#412](https://github.com/neuro-inc/neuro-flow/issues/412))

- Added automatic creation of parent directories in `neuro-flow upload` command. ([#416](https://github.com/neuro-inc/neuro-flow/issues/416))

- Added cancellation of image build jobs if bake is cancelled or failed. ([#423](https://github.com/neuro-inc/neuro-flow/issues/423))

- Added `force_rebuild` flag to image section in yaml config. ([#424](https://github.com/neuro-inc/neuro-flow/issues/424))

- Added new options to neuro-flow bakes:
  - `--since DATE_OR_TIMEDELTA` to show bakes that were created after specified moment
  - `--until DATE_OR_TIMEDELTA` to show bakes that were created before specified moment
  - `--recent-first/--recent-last` to alter ordering in the result table ([#428](https://github.com/neuro-inc/neuro-flow/issues/428))

- Pre-fetch the last attempt in bakes list to speed up the command. ([#429](https://github.com/neuro-inc/neuro-flow/issues/429))


Bugfixes
--------


- Fixed auto-generation of suffixes for multi jobs in live mode. ([#415](https://github.com/neuro-inc/neuro-flow/issues/415))

- Fixed overriding param with empty value, `--param name ""` works properly now. ([#417](https://github.com/neuro-inc/neuro-flow/issues/417))

- Fixed EvalError when tried to access `ref`, `ref_rw`, `ref_ro` of volume context. ([#418](https://github.com/neuro-inc/neuro-flow/issues/418))


Neuro Flow 21.5.19 (2021-05-19)
===============================

Bugfixes
--------

- Fix a bug with processing SKIPPED task


Neuro Flow 21.5.17 (2021-05-17)
===============================

Features
--------

- Neuro Flow now uses the dedicated Platform API to store the flow database. The storage is still supported but will be removed in a few months.

- Added new expressions functions:
  - `values(dict_instance)`: get values of dictionary (similar to python's `dict_instance.values()`)
  - `str(any)`: convert any object to string
  - `replace(string, old, new)`: replace all occurrences of `old` in `string` with `new`.
  - `join(separator, array)`: concatenate array of strings inserting `separator` in between. ([#357](https://github.com/neuro-inc/neuro-flow/issues/357))

- Added support of default volumes similar to default env: both in live and batch modes, you can
  specify them under `defaults` section:
  ```
  defaults:
	volumes:
	  - storage:some/dir:/mnt/some/dir
	  - storage:some/another/dir:/mnt/some/another/dir
  ```
  - In live mode such volumes will be added to all jobs.
  - In batch mode such volumes will be added to all tasks.

  Default volumes are not passed to actions (same as default env). ([#359](https://github.com/neuro-inc/neuro-flow/issues/359))

- Added passing of global options (`-v`, `-q`, `--show-traceback`) to neuro cli and executor. ([#360](https://github.com/neuro-inc/neuro-flow/issues/360))

- Added `--dry-run` flag for `neuro-flow run` that enables prints job command instead of running it. ([#362](https://github.com/neuro-inc/neuro-flow/issues/362))

- Added support of tagging bakes.

  To tag a bake:
  ```
  neuro bake --tag tag1 --tag tag2 batch_name
  ```
  To retrieve bakes by tags:
  ```
  neuro bakes --tag tag1
  ``` ([#382](https://github.com/neuro-inc/neuro-flow/issues/382))


Bugfixes
--------


- Fixed bug that led to crash in `neuro-flow inspect` when bake had cached task. ([#358](https://github.com/neuro-inc/neuro-flow/issues/358))

- Support click 8.0 ([#407](https://github.com/neuro-inc/neuro-flow/issues/407))

Neuro Flow 21.4.5 (2021-04-05)
==============================

Features
--------


- Mark cached task in `neuro-flow inspect <bake>` as "cached" instead of "succeeded". ([#318](https://github.com/neuro-inc/neuro-flow/issues/318))

- Auto create parent directories in "upload()" expression function. ([#319](https://github.com/neuro-inc/neuro-flow/issues/319))

- Add bake_id tag to jobs started by bake inside neuro platform. ([#320](https://github.com/neuro-inc/neuro-flow/issues/320))

- Add tags to remote executor jobs. The tags are: "project:project_id", "flow:flow_name", "bake:bake_id",
  "remote_executor". ([#321](https://github.com/neuro-inc/neuro-flow/issues/321))

- Print name of the action in error about unexpected needs entry, for example:
  ```
  ERROR: Action 'ws:some_action' does not contain task 'wrong_task_name'
  ``` ([#323](https://github.com/neuro-inc/neuro-flow/issues/323))

- Added printing of filename in expression evaluation errors. ([#324](https://github.com/neuro-inc/neuro-flow/issues/324))

- Dropped `outputs.needs` in batch actions. Made all action task results available for calculation action needs.
  This avoids confusing behavior when action can succeed even when some of its tasks have failed. ([#325](https://github.com/neuro-inc/neuro-flow/issues/325))

- Add support of empty list and dict (`[]` and `{}`) in expressions. ([#333](https://github.com/neuro-inc/neuro-flow/issues/333))

- Added validation of tasks `needs` property. ([#334](https://github.com/neuro-inc/neuro-flow/issues/334))

- Added validation of action arguments before starting a bake. ([#336](https://github.com/neuro-inc/neuro-flow/issues/336))

- Implemented marking of bake as failed when an error happens during the batch execution. If the error is caused
  because of SIGINT, the bake will be marked as cancelled instead of failed. ([#338](https://github.com/neuro-inc/neuro-flow/issues/338))

- Allow to specify timeout for executor job in yaml and increase default lifespan to 7d. Example:
  ```
  kind: batch
  life_span: 30d
  tasks:
	...
  ``` ([#339](https://github.com/neuro-inc/neuro-flow/issues/339))

- Add support of local actions inside of batch actions if they do not depend on any remote tasks. ([#340](https://github.com/neuro-inc/neuro-flow/issues/340))


Bugfixes
--------


- Use 1-based indexes instead of 0-based for lines and columns in error messages. ([#335](https://github.com/neuro-inc/neuro-flow/issues/335))


Neuro Flow 21.3.17 (2021-03-17)
===============================

Bugfixes
--------


- Fix executor restart when there is a action that should be marked as ready. ([#315](https://github.com/neuro-inc/neuro-flow/issues/315))


Neuro Flow 21.3.3 (2021-03-03)
==============================

Features
--------


- Add support of parsing batch params from file. ([#295](https://github.com/neuro-inc/neuro-flow/issues/295))


Bugfixes
--------


- Added proper error message for the hosted on GitHub actions, which reference is wrong (URL leads to 404). ([#294](https://github.com/neuro-inc/neuro-flow/issues/294))

- Fix processing of bake that has actions that use another bake action. ([#302](https://github.com/neuro-inc/neuro-flow/issues/302))


Neuro Flow 21.2.16 (2021-02-16)
===============================

Bugfixes
--------

- Fixed parsing of needs in actions


Neuro Flow 21.2.11.1 (2021-02-11)
=================================

Bugfixes
--------


- Enable restarting of remote executor jobs on failure.


Neuro Flow 21.2.11 (2021-02-11)
===============================

Features
--------


- Support dependencies on running tasks along with finished ones in batch mode. ([#255](https://github.com/neuro-inc/neuro-flow/issues/281))


Bugfixes
--------


- Fix windows path issue. ([#261](https://github.com/neuro-inc/neuro-flow/issues/289))


Neuro Flow 21.1.4 (2021-01-04)
==============================

Features
--------


- Implement `inspect_job()` expression function. ([#255](https://github.com/neuro-inc/neuro-flow/issues/255))


Bugfixes
--------


- Fix ignoring of workdir in batch mode. ([#261](https://github.com/neuro-inc/neuro-flow/issues/261))


Neuro Flow 20.12.16 (2020-12-16)
================================

Bugfixes
--------


- Fixed operator precedence: previously all operators had same precedence. Made `or` and `and`
  operate as logical operators instead of bitwise. ([#239](https://github.com/neuro-inc/neuro-flow/issues/239))

- Forbid passing args into a job, volumes into an action etc. ([#241](https://github.com/neuro-inc/neuro-flow/issues/241))


Neuro Flow 20.12.8 (2020-12-08)
===============================

Features
--------


- Allow schedule timeout parameterization in the flow description; useful in cases, when the job should be launched on scarce resources. ([#202](https://github.com/neuro-inc/neuro-flow/issues/202))

- Allow image overwrite by forwarding the `--force-overwrite` flag to the underlying `neuro-extras image build` command. ([#203](https://github.com/neuro-inc/neuro-flow/issues/203))

- Support of preset parameterization for image build job; now user could change the hardware environment for image build. ([#204](https://github.com/neuro-inc/neuro-flow/issues/204))

- Implement `parse_volume()` expression function. ([#217](https://github.com/neuro-inc/neuro-flow/issues/217))

- Support compound expressions for `volumes`, `tags`, `env`, `port_forward` attributes:

  ```
  jobs:
	job_a:
	  volumes: "${{ ['ubuntu', volumes.volume_a.ref] }}"
  ``` ([#236](https://github.com/neuro-inc/neuro-flow/issues/236))


Neuro Flow 20.11.24 (2020-11-24)
================================

Bugfixes
--------


- Fix ``hash_files()`` function: it is faster, hashes the whole file instead of the first 256 KiB, and includes processed filenames into the hash. ([#190](https://github.com/neuro-inc/neuro-flow/issues/190))


Neuro Flow 20.11.10 (2020-11-10)
================================

Features
--------


- Rework output of `neuro bake` command; now with timestamps and progress bars. ([#172](https://github.com/neuro-inc/neuro-flow/issues/172))


Neuro Flow 20.11.3 (2020-11-03)
===============================

Features
--------


- Added validation of `outputs.needs` in batch actions. ([#163](https://github.com/neuro-inc/neuro-flow/issues/163))

- Store a JSON with live jobs configuration on every run job start. ([#170](https://github.com/neuro-inc/neuro-flow/issues/170))

- Implement ``lower()`` and ``upper()`` expression functions, e.g.  ``ref: image:${{ lower(flow.project_id) }}:v1.0`` ([#174](https://github.com/neuro-inc/neuro-flow/issues/174))


Bugfixes
--------


- Don't raise an error in `neuro-flow run` if the remote folder for the project already exists ([#184](https://github.com/neuro-inc/neuro-flow/issues/184))


Neuro Flow 20.10.26 (2020-10-26)
================================

Features
--------


- Improve inspect command: sort output by task creation time, add columns with task start and task finish times. ([#156](https://github.com/neuro-inc/neuro-flow/issues/156))


Bugfixes
--------


- Fix variable substitution for printed text for bake cancellation ([#152](https://github.com/neuro-inc/neuro-flow/issues/152))

- Add forgotten restart command ([#160](https://github.com/neuro-inc/neuro-flow/issues/160))


Neuro Flow 20.10.21 (2020-10-21)
================================

Features
--------


- Sort bakes by creation time. ([#147](https://github.com/neuro-inc/neuro-flow/issues/147))

- Support pass_config: true YAML option for task/job ([#151](https://github.com/neuro-inc/neuro-flow/issues/151))


Bugfixes
--------


- Ignore hidden files and folders (e.g. .cache) when getting the list of bakes ([#146](https://github.com/neuro-inc/neuro-flow/issues/146))


Neuro Flow 20.10.19 (2020-10-19)
================================

Features
--------


- Added `--show-traceback` option. ([#134](https://github.com/neuro-inc/neuro-flow/issues/134))

- Tune a message about bake starting ([#135](https://github.com/neuro-inc/neuro-flow/issues/135))


Bugfixes
--------


- Fix noisy error report for `neuro kill ALL` command. ([#136](https://github.com/neuro-inc/neuro-flow/issues/136))

- Fix invariant by saving both started and finished records for cached task ([#139](https://github.com/neuro-inc/neuro-flow/issues/139))


Neuro Flow 20.10.16 (2020-10-16)
================================

Features
--------


- Added --param option to `neuro-flow bake` command that allows to pass arguments to `params` section
  of the config file. ([#128](https://github.com/neuro-inc/neuro-flow/issues/128))

- Added --param option to `neuro-flow run` command that allows to pass arguments to `param` section
  of the job in config file. ([#132](https://github.com/neuro-inc/neuro-flow/issues/132))

- Added `upload()` function to re-upload volumes just before starting job in live mode. ([#133](https://github.com/neuro-inc/neuro-flow/issues/133))


Neuro Flow 20.10.14 (2020-10-14)
================================

No significant changes.


Neuro Flow 20.10.12 (2020-10-12)
================================

Bugfixes
--------


- Fix inspect command when there is a started but not finished action ([#122](https://github.com/neuro-inc/neuro-flow/issues/122))

- Fixed not marking cached task as done ([#123](https://github.com/neuro-inc/neuro-flow/issues/123))
