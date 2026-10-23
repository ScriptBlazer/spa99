def system(request):
    """System pages only: the environment label for the title bar and stripe (settings.SYSTEM_ENV_LABEL: DEV or LIVE)."""
    from django.conf import settings

    if getattr(request, "urlconf", "") != "config.urls_system":
        return {}
    return {"system_env": settings.SYSTEM_ENV_LABEL.lower()}
