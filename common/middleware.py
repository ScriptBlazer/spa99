from django.conf import settings


class HostRoutingMiddleware:
    """Serve each Spa 99 site on its own host.

    OFFICE_HOST uses config.urls_office (the business back office), CONTROL_HOST uses config.urls_control (the
    building control room, parked); everything else uses config.urls. Sessions are per host, so a login on one host
    never logs you into another. The two staff hosts are never indexed (X-Robots-Tag).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":")[0].lower()  # raises DisallowedHost for unknown hosts
        staff_host = True
        if host == settings.OFFICE_HOST.lower():
            request.urlconf = "config.urls_office"
        elif host == settings.CONTROL_HOST.lower():
            request.urlconf = "config.urls_control"
        else:
            request.urlconf, staff_host = "config.urls", False
        response = self.get_response(request)
        if staff_host:
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response
