from .types import LocalPath


# A storage abstraction
#
# There is a possibility to add Postgres storage class later, for example


class BatchStorage:
    def __init__(self, path: LocalPath) -> None:
        self._path = path

    def init(self, workspace: LocalPath, config_file: LocalPath) -> None:
        pass

    def check_batch(self, config_file: LocalPath) -> None:
        pass
