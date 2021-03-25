Dropped `outputs.needs` in batch actions. Made all action task results available for calculation action needs.
This avoids confusing behavior when action can succeed even when some of its tasks have failed.
