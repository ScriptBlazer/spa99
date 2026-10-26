from . import sales


class SalePreviewMiddleware:
    """Reads `?sale_preview=<token>` on the public site (after the session is loaded). Does nothing, and costs nothing, without it."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if sales.PREVIEW_PARAM in request.GET and sales.is_public_host(request):
            sales.start_preview(request)
        return self.get_response(request)
