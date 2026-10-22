from django.conf import settings


class HostRoutingMiddleware:
    """Serve Spa 99 Control on its own host.

    Requests for settings.CONTROL_HOST use config.urls_control; everything else uses config.urls.
    Sessions are per host, so a login on one host never logs you into the other.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":")[0].lower()  # raises DisallowedHost for unknown hosts
        request.urlconf = "config.urls_control" if host == settings.CONTROL_HOST.lower() else "config.urls"
        return self.get_response(request)
