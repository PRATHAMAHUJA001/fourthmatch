"""Test isolation: never write uploaded policies or evidence into the real storage/."""
from __future__ import annotations

import os
import tempfile

# Must run before app.core.config.get_settings() is first called (app.main does at import).
os.environ.setdefault("STORAGE_ROOT", tempfile.mkdtemp(prefix="fm-test-storage-"))
