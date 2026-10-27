"""Shared resource limits for single and exhaustive backtest requests."""
import os
MAX_WORKERS=max(1,min(8,(os.cpu_count() or 1)-1))
DEFAULT_WORKERS=min(4,MAX_WORKERS)
