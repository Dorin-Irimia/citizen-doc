from django.utils.deprecation import MiddlewareMixin


class NoCacheForAuthMiddleware(MiddlewareMixin):
    """
    Previne afisarea din cache a paginilor protejate.
    Astfel, la back/forward in browser se forteaza revalidarea autentificarii.
    """

    def process_response(self, request, response):
        # Aplicam pentru utilizatori autentificati sau pentru rutele cu sesiune
        if request.user.is_authenticated:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
