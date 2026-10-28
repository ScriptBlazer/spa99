from . import sales


class SalePreviewMiddleware:
    """Ends the preview on `?sale_preview=end` (public site, after the session is loaded). Starting one is a POST (plans.views.preview_start)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.GET.get(sales.PREVIEW_PARAM) == "end" and sales.is_public_host(request):
            sales.end_preview(request)
        return self.get_response(request)
