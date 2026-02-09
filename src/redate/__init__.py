"""
ReDate: Production-grade News Aggregation & Publishing Platform.

Top-level package exposing core service entry points and version information.
Designed for both CLI usage and library integration.
"""

from .adapter_storage import HybridStorageAdapter
from .main import app, bootstrap
from .service_migration import MigrationService
from .service_news import NewsService

__all__ = [
    "HybridStorageAdapter",
    "MigrationService",
    "NewsService",
    "app",
    "bootstrap",
]
__version__ = "0.3.0"
