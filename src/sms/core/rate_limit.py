from slowapi import Limiter
from slowapi.util import get_remote_address

# Per-IP by default (get_remote_address). Applied selectively per route via
# @limiter.limit(...) — not every route needs it, login does (see ADR 0008).
limiter = Limiter(key_func=get_remote_address)
