"""Product resource boundary for user-visible resource projections."""

from __future__ import annotations

import sys

from backend import resource_provider_boundary as _resource_provider_boundary

sys.modules[__name__] = _resource_provider_boundary
