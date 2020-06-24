Proposed commands
=================

The examples from this file uses `flow` command which is available as `neuro flow`.


`flow` reads configuration from a file specified by `--config <config-file.yml>` option.
The default can be specified by global/local neuromation config, e.g. `.neuro.toml`.


List status of jobs from this flow
-----------------------------------

  flow --config <config-file.yml> ps
  
Command lists all jobs that belongs to the configuration.  Additional restrictions like
job name and user name may be applied as optional arguments.


Start a job
-----------

Run specific job:

  flow --config <config-file.yml> run <name>
  
There is a theoretical possibility to run all jobs enumerated by `config-file.yml` but
the need is very dubious.

View logs
---------

  flow --config <config-file.yml> logs <name>
  
Kill job
--------

  flow --config <config-file.yml> kill <name>
  
or

  flow --config <config-file.yml> kill --all
  
Build image
-----------

  flow --config <config-file.yml> build <image-name>


Port forward
-------------

  flow --config <config-file.yml> port-forward <name> [--localport xxx --remote-port yyy]

Upload/download data?
---------------------

Is data belong to a project or not?

Code sync should be performed via github probably. Code is not stored on the storage ideally.
