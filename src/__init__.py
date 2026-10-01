"""Reconciliation source package."""

import os
# Prevent OpenBLAS memory allocation retries on Windows
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
