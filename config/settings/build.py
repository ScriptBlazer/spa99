"""Image build only: `collectstatic` in the Dockerfile. Same static setup as live (hashed manifest files, DEBUG off) but
needs no secrets, so nothing secret or fake is ever baked into the image. Never used to serve requests."""
from .base import *  # noqa: F401,F403

STARTUP_REPORT = None  # quiet build log
