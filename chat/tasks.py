"""The daily clean-up (registered in common/management/commands/register_schedules.py)."""
from common.jobs import tracked

from . import services


@tracked("chat_prune")
def prune_scheduled():
    return f"deleted {services.prune()} chat(s) older than the retention"
