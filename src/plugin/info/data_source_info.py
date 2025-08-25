from spaceone.api.cost_analysis.plugin import data_source_pb2
from spaceone.core.pygrpc.message_type import *

__all__ = ["plugin_info"]


def plugin_info(plugin_data):
    info = {
        "metadata": change_struct_type(plugin_data["metadata"]),
    }

    return data_source_pb2.PluginInfo(**info)
