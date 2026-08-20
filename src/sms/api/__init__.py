"""The single router aggregator — main.py only ever imports from here, so
the entrypoint never grows with the domain count."""

from sms.api.router import api_router

__all__ = ["api_router"]
