from apolo_sdk import PluginManager


APOLO_FLOW_UPGRADE = """\
You are using Neuro Flow {old_ver}, however {new_ver} is available.
You should consider upgrading via the following command:
    python -m pip install --upgrade neuro-flow
"""


def get_apolo_flow_txt(old: str, new: str) -> str:
    return APOLO_FLOW_UPGRADE.format(old_ver=old, new_ver=new)


def setup(manager: PluginManager) -> None:
    manager.version_checker.register("neuro-flow", get_apolo_flow_txt)
