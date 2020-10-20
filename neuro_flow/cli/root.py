import dataclasses

from neuro_flow.parser import ConfigDir


@dataclasses.dataclass(frozen=True)
class Root:
    config_dir: ConfigDir
