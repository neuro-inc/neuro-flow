Implemented marking of bake as failed when an error happens during the batch execution. If the error is caused
because of SIGINT, the bake will be marked as cancelled instead of failed.
