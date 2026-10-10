"""Phase 1 evaluation package: task specs, isolated workspaces, executors,
independent judge, traces, metrics, baseline policies. Offline-first; the live
path is closed until a separate Planner plan authorizes budget."""

from .task_spec import TaskSpec, load_task, load_all_tasks  # noqa: F401
