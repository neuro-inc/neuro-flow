Added new context called git. It has following attributes:

- ${{ git.sha }} -- SHA of current commit
- ${{ git.branch }} - name of current branch
- ${{ git.tags }} - list of tags that point to current commit

This context is available everywhere both in live and batch mode, but it can only be used
if project's workspace is inside some git repository.
