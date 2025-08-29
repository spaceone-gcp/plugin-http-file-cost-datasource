import functools

from spaceone.api.cost_analysis.plugin import job_pb2
from spaceone.core.pygrpc.message_type import change_struct_type

__all__ = ["task_info", "tasks_info", "changed_info"]


def task_info(task_data):
    info = {"task_options": change_struct_type(task_data["task_options"])}

    return job_pb2.TaskInfo(**info)


def changed_info(changed_data):
    info = {"start": changed_data["start"]}

    if "end" in changed_data:
        info["end"] = changed_data["end"]

    return job_pb2.ChangedInfo(**info)


def tasks_info(result, **kwargs):
    tasks_data = result.get("tasks", [])
    changed_data = result.get("changed", [])

    return job_pb2.TasksInfo(
        tasks=list(map(functools.partial(task_info, **kwargs), tasks_data)),
        changed=list(map(functools.partial(changed_info, **kwargs), changed_data)),
    )
