"""Internal workspace navigation shared by the legacy authentication routes."""
from urllib.parse import unquote, urlsplit


def internal_redirect(value):
    target = str(value or '').strip()
    decoded = unquote(target)
    parsed = urlsplit(decoded)
    if (not decoded.startswith('/') or decoded.startswith('//') or '\\' in decoded
            or any(ord(char) < 32 for char in decoded) or parsed.scheme or parsed.netloc):
        return '/management'
    if parsed.path.startswith(('/login', '/register', '/auth/', '/api/auth/')):
        return '/management'
    return target
