"""Gold figures follow the Gold rows through model signals, not only through the services: Barry's Gold status can also
be changed in the Django admin (and erased by the GDPR delete), and those paths must move the figures too. Everything
else (registrations, journeys, verification) is counted in the services. The handlers run inside the saving
transaction, so a rolled-back save leaves the figures untouched."""
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from . import metrics
from .metrics import K


def _stash(instance, fields):
    """Remember the stored values before the save so post_save can tell what changed."""
    old = None
    if instance.pk and not instance._state.adding:
        old = type(instance).objects.filter(pk=instance.pk).values(*fields).first()
    instance._metrics_before = old


@receiver(pre_save, sender="gold.GoldApplication", dispatch_uid="insights_gold_application_pre")
def application_pre_save(sender, instance, update_fields=None, **kwargs):
    _stash(instance, ["status", "potential_level", "approved_at"])


@receiver(post_save, sender="gold.GoldApplication", dispatch_uid="insights_gold_application_post")
def application_post_save(sender, instance, created, **kwargs):
    old = getattr(instance, "_metrics_before", None)
    if created or old is None:
        if created:
            metrics.gold_application(instance.created_at, instance.potential_level, instance.status)
        return
    if old["status"] != instance.status:
        metrics.gold_status_changed(old["status"], instance.status, instance.approved_at or old["approved_at"])
    metrics.gold_potential_changed(old["potential_level"], instance.potential_level, instance.created_at)


@receiver(post_delete, sender="gold.GoldApplication", dispatch_uid="insights_gold_application_delete")
def application_deleted(sender, instance, **kwargs):
    metrics.gold_application(instance.created_at, instance.potential_level, instance.status, amount=-1)
    if instance.status == "approved":
        metrics.count(K.GOLD_APPROVED, "", -1, metrics.day(instance.approved_at or instance.updated_at))


@receiver(pre_save, sender="gold.GoldInvite", dispatch_uid="insights_gold_invite_pre")
def invite_pre_save(sender, instance, **kwargs):
    _stash(instance, ["sent_at", "used_at"])


@receiver(post_save, sender="gold.GoldInvite", dispatch_uid="insights_gold_invite_post")
def invite_post_save(sender, instance, created, **kwargs):
    old = getattr(instance, "_metrics_before", None) or {"sent_at": None, "used_at": None}
    if instance.sent_at and not old["sent_at"]:
        metrics.gold_invite(K.GOLD_INVITES_SENT, instance.sent_at)
    if instance.used_at and not old["used_at"]:
        metrics.gold_invite(K.GOLD_INVITES_USED, instance.used_at)


@receiver(post_delete, sender="gold.GoldInvite", dispatch_uid="insights_gold_invite_delete")
def invite_deleted(sender, instance, **kwargs):
    if instance.sent_at:
        metrics.gold_invite(K.GOLD_INVITES_SENT, instance.sent_at, amount=-1)
    if instance.used_at:
        metrics.gold_invite(K.GOLD_INVITES_USED, instance.used_at, amount=-1)


# ---------- plan interest (the Django admin can change the plan; the services save through the same path) ----------

@receiver(pre_save, sender="users.InterestRegistration", dispatch_uid="insights_interest_pre")
def interest_pre_save(sender, instance, **kwargs):
    _stash(instance, ["plan_id"])


@receiver(post_save, sender="users.InterestRegistration", dispatch_uid="insights_interest_post")
def interest_post_save(sender, instance, created, **kwargs):
    old = getattr(instance, "_metrics_before", None)
    if created or old is None or old["plan_id"] == instance.plan_id:
        return  # creation is counted by the services (they know the source and marketing choice)
    from plans.models import Plan

    slugs = dict(Plan.objects.filter(pk__in=[p for p in (old["plan_id"], instance.plan_id) if p]).values_list("pk", "slug"))
    metrics.interest_plan_changed(slugs.get(old["plan_id"]), slugs.get(instance.plan_id), instance.created_at)


@receiver(post_save, sender="insights.OfficeGoal", dispatch_uid="insights_goal_saved")
@receiver(post_delete, sender="insights.OfficeGoal", dispatch_uid="insights_goal_deleted")
def goal_changed(sender, **kwargs):
    """A goal edited in the admin moves the rings' percentages: refresh the stored snapshots."""
    from office import snapshots

    snapshots.request_refresh()
