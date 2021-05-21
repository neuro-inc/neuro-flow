Added image building functionality to batch mode.
The `images` yaml section entries with `context` and `dockerfile` are now allowed
both in batch and batch action config files.
Image build starts automatically when task that uses it is ready to be run.
