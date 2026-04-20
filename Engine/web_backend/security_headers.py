"""Security headers middleware (§16 hardening, 2026-04-20).

Sets conservative browser-security headers on every HTTP response:

  - Strict-Transport-Security : force HTTPS for 2 years, preload-eligible
  - Content-Security-Policy   : restrict script/style/frame/connect origins
  - X-Content-Type-Options    : block MIME sniffing
  - X-Frame-Options           : deny framing (belt-and-suspenders with CSP
                                frame-ancestors for older browsers)
  - Referrer-Policy           : send origin only when downgrading to HTTP
  - Permissions-Policy        : disable features we don't use
                                (geolocation, mic, camera, payment)

Design notes:
  - 'unsafe-inline' is retained for style-src and script-src because
    html_reading.py, unified_view.py, admin.html, and success.html all
    embed inline <style> and <script> blocks. Moving to nonces is a
    future hardening pass; 'unsafe-inline' is still better than no CSP.
  - Fonts come from fonts.googleapis.com (stylesheets) and
    fonts.gstatic.com (woff2 files). Those are explicit in the policy.
  - connect-src 'self' covers success.html's fetch() polling and
    admin.html's /api/internal/metrics calls.
  - img-src allows data: URIs for future inline SVG/base64 images.
  - frame-ancestors 'none' + X-Frame-Options: DENY prevents clickjacking.
  - upgrade-insecure-requests forces any stray http:// subresources to https.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


# The CSP is kept as a single well-formatted string so future edits are
# obvious. Each directive is on its own line in the source for diff clarity;
# joined with `; ` at runtime.
_CSP_DIRECTIVES = [
    "default-src 'self'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "script-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "connect-src 'self'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "upgrade-insecure-requests",
]

CSP_HEADER = "; ".join(_CSP_DIRECTIVES)

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "Content-Security-Policy": CSP_HEADER,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Append the SECURITY_HEADERS dict to every response.

    Response-time middleware: runs AFTER route handlers, so it applies
    uniformly to HTMLResponse, FileResponse, JSONResponse, and error
    responses from the exception handler chain.

    If a handler sets one of these headers explicitly, we DON'T overwrite —
    the handler wins. Lets individual routes narrow the policy if needed
    (e.g., a future /embed endpoint that needs frame-ancestors to be set).
    """

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            if header not in response.headers:
                response.headers[header] = value
        return response
