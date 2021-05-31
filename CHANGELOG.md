[comment]: # (Please do not modify this file)
[comment]: # (Put you comments to changelog.d and it will be moved to changelog in next release)

[comment]: # (Clear the text on make release for canceling the release)

[comment]: # (towncrier release notes start)

Neuro_Flow 21.5.31 (2021-05-31)
===============================

Bugfixes
--------


- Fix broken cache when using images: now remote context dir name is based on image ref instead of random name. ([#422](https://github.com/neuro-inc/neuro-flow/issues/422))

- Fix a error that leads to bakes cache check miss even if the record is present in cache actually. ([#441](https://github.com/neuro-inc/neuro-flow/issues/441))


Neuro_Flow 21.5.25 (2021-05-25)
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


Neuro_Flow 21.5.19 (2021-05-19)
===============================

Bugfixes
--------

- Fix a bug with processing SKIPPED task


Neuro_Flow 21.5.17 (2021-05-17)
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

Neuro_Flow 21.4.5 (2021-04-05)
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


Neuro_Flow 21.3.17 (2021-03-17)
===============================

Bugfixes
--------


- Fix executor restart when there is a action that should be marked as ready. ([#315](https://github.com/neuro-inc/neuro-flow/issues/315))


Neuro_Flow 21.3.3 (2021-03-03)
==============================

Features
--------


- Add support of parsing batch params from file. ([#295](https://github.com/neuro-inc/neuro-flow/issues/295))


Bugfixes
--------


- Added proper error message for the hosted on GitHub actions, which reference is wrong (URL leads to 404). ([#294](https://github.com/neuro-inc/neuro-flow/issues/294))

- Fix processing of bake that has actions that use another bake action. ([#302](https://github.com/neuro-inc/neuro-flow/issues/302))


Neuro_Flow 21.2.16 (2021-02-16)
===============================

Bugfixes
--------

- Fixed parsing of needs in actions


Neuro_Flow 21.2.11.1 (2021-02-11)
=================================

Bugfixes
--------


- Enable restarting of remote executor jobs on failure.


Neuro_Flow 21.2.11 (2021-02-11)
===============================

Features
--------


- Support dependencies on running tasks along with finished ones in batch mode. ([#255](https://github.com/neuro-inc/neuro-flow/issues/281))


Bugfixes
--------


- Fix windows path issue. ([#261](https://github.com/neuro-inc/neuro-flow/issues/289))


Neuro_Flow 21.1.4 (2021-01-04)
==============================

Features
--------


- Implement `inspect_job()` expression function. ([#255](https://github.com/neuro-inc/neuro-flow/issues/255))


Bugfixes
--------


- Fix ignoring of workdir in batch mode. ([#261](https://github.com/neuro-inc/neuro-flow/issues/261))


Neuro_Flow 20.12.16 (2020-12-16)
================================

Bugfixes
--------


- Fixed operator precedence: previously all operators had same precedence. Made `or` and `and`
  operate as logical operators instead of bitwise. ([#239](https://github.com/neuro-inc/neuro-flow/issues/239))

- Forbid passing args into a job, volumes into an action etc. ([#241](https://github.com/neuro-inc/neuro-flow/issues/241))


Neuro_Flow 20.12.8 (2020-12-08)
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


Neuro_Flow 20.11.24 (2020-11-24)
================================

Bugfixes
--------


- Fix ``hash_files()`` function: it is faster, hashes the whole file instead of the first 256 KiB, and includes processed filenames into the hash. ([#190](https://github.com/neuro-inc/neuro-flow/issues/190))


Neuro_Flow 20.11.10 (2020-11-10)
================================

Features
--------


- Rework output of `neuro bake` command; now with timestamps and progress bars. ([#172](https://github.com/neuro-inc/neuro-flow/issues/172))


Neuro_Flow 20.11.3 (2020-11-03)
===============================

Features
--------


- Added validation of `outputs.needs` in batch actions. ([#163](https://github.com/neuro-inc/neuro-flow/issues/163))

- Store a JSON with live jobs configuration on every run job start. ([#170](https://github.com/neuro-inc/neuro-flow/issues/170))

- Implement ``lower()`` and ``upper()`` expression functions, e.g.  ``ref: image:${{ lower(flow.project_id) }}:v1.0`` ([#174](https://github.com/neuro-inc/neuro-flow/issues/174))


Bugfixes
--------


- Don't raise an error in `neuro-flow run` if the remote folder for the project already exists ([#184](https://github.com/neuro-inc/neuro-flow/issues/184))


Neuro_Flow 20.10.26 (2020-10-26)
================================

Features
--------


- Improve inspect command: sort output by task creation time, add columns with task start and task finish times. ([#156](https://github.com/neuro-inc/neuro-flow/issues/156))


Bugfixes
--------


- Fix variable substitution for printed text for bake cancellation ([#152](https://github.com/neuro-inc/neuro-flow/issues/152))

- Add forgotten restart command ([#160](https://github.com/neuro-inc/neuro-flow/issues/160))


Neuro_Flow 20.10.21 (2020-10-21)
================================

Features
--------


- Sort bakes by creation time. ([#147](https://github.com/neuro-inc/neuro-flow/issues/147))

- Support pass_config: true YAML option for task/job ([#151](https://github.com/neuro-inc/neuro-flow/issues/151))


Bugfixes
--------


- Ignore hidden files and folders (e.g. .cache) when getting the list of bakes ([#146](https://github.com/neuro-inc/neuro-flow/issues/146))


Neuro_Flow 20.10.19 (2020-10-19)
================================

Features
--------


- Added `--show-traceback` option. ([#134](https://github.com/neuro-inc/neuro-flow/issues/134))

- Tune a message about bake starting ([#135](https://github.com/neuro-inc/neuro-flow/issues/135))


Bugfixes
--------


- Fix noisy error report for `neuro kill ALL` command. ([#136](https://github.com/neuro-inc/neuro-flow/issues/136))

- Fix invariant by saving both started and finished records for cached task ([#139](https://github.com/neuro-inc/neuro-flow/issues/139))


Neuro_Flow 20.10.16 (2020-10-16)
================================

Features
--------


- Added --param option to `neuro-flow bake` command that allows to pass arguments to `params` section
  of the config file. ([#128](https://github.com/neuro-inc/neuro-flow/issues/128))

- Added --param option to `neuro-flow run` command that allows to pass arguments to `param` section
  of the job in config file. ([#132](https://github.com/neuro-inc/neuro-flow/issues/132))

- Added `upload()` function to re-upload volumes just before starting job in live mode. ([#133](https://github.com/neuro-inc/neuro-flow/issues/133))


Neuro_Flow 20.10.14 (2020-10-14)
================================

No significant changes.


Neuro_Flow 20.10.12 (2020-10-12)
================================

Bugfixes
--------


- Fix inspect command when there is a started but not finished action ([#122](https://github.com/neuro-inc/neuro-flow/issues/122))

- Fixed not marking cached task as done ([#123](https://github.com/neuro-inc/neuro-flow/issues/123))
