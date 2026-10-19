"""Shared test setup. Runs before any test module imports the app.

API tests use a separate database (`segmentation_test`) and a temporary uploads folder, so running
the tests never touches your development data. Real environment variables beat .env, so setting them
here redirects the app.
"""

import os
import tempfile

os.environ.setdefault("SEGMENTATION_DATABASE_URL", "postgresql+psycopg://segmentation:segmentation@localhost:5432/segmentation_test")
os.environ["SEGMENTATION_STORAGE_DIR"] = tempfile.mkdtemp(prefix="human-cutout-test-")
os.environ["SEGMENTATION_CHECKPOINT_PATH"] = "does-not-exist.pth"  # tests use a fake model instead
