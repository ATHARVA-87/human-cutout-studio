"""Shared test setup. Runs before any test module imports the app.

API tests use a separate database (default `segmentation_test`) and a temporary uploads folder, so
running the tests never touches your development or production data. The app reads its database from
SEGMENTATION_DATABASE_URL, so we overwrite it here (from TEST_DATABASE_URL), even if your shell has
exported a production URL for scripts/db_admin.py.
"""

import os
import tempfile

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://segmentation:segmentation@localhost:5432/segmentation_test")
if not TEST_DATABASE_URL.rsplit("/", 1)[-1].split("?")[0].endswith("_test"):
    raise RuntimeError(f"Refusing to run tests against a database whose name does not end in _test: {TEST_DATABASE_URL}")

os.environ["SEGMENTATION_DATABASE_URL"] = TEST_DATABASE_URL
os.environ["SEGMENTATION_STORAGE_DIR"] = tempfile.mkdtemp(prefix="human-cutout-test-")
os.environ["SEGMENTATION_MODEL_PATH"] = "does-not-exist.onnx"  # API tests use a fake model instead
