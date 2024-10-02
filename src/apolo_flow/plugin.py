from apolo_sdk import PluginManager


APOLO_FLOW_UPGRADE = """\
You are using Apolo Flow {old_ver}, however {new_ver} is available.
You should consider upgrading via the following command:
    python -m pip install --upgrade apolo-flow
"""


def get_apolo_flow_txt(old: str, new: str) -> str:
    return APOLO_FLOW_UPGRADE.format(old_ver=old, new_ver=new)


def setup(manager: PluginManager) -> None:
    manager.version_checker.register("apolo-flow", get_apolo_flow_txt)
