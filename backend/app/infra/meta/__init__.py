"""Meta model client wrappers. Shapes only from docs/MODEL_NOTES.md."""
from app.infra.meta.client import MetaModelClient, call_model, get_shared_client

__all__ = ["MetaModelClient", "call_model", "get_shared_client"]
