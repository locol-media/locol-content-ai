"""Environment-driven settings for the UI test suite.

Everything here is overridable so the same page objects can be pointed at a local
run, a container, or a cluster deployment without touching test code. The defaults
match the local development setup documented in docs/deploy-local.md (Web on 8501,
BackEnd on 8000).
"""
import os


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


# The Streamlit app - login, surveys, campaign projects, config manager.
WEB_URL = _env("QA_WEB_URL", "http://localhost:8501").rstrip("/")

# BackEnd, which also serves the Content Editor's static assets under /www.
API_URL = _env("QA_API_URL", "http://localhost:8000").rstrip("/")

# Account the tests sign in as.
USERNAME = _env("QA_USERNAME", "user01")
PASSWORD = _env("QA_PASSWORD", "user01")

# Milliseconds. Streamlit reruns the whole script on every interaction, so even
# trivial clicks involve a websocket round trip.
DEFAULT_TIMEOUT = int(_env("QA_TIMEOUT_MS", "15000"))

# Anything that calls an LLM (story ideas, campaign brainstorm, content
# generation) is measured in minutes. BackEnd's own ceiling is
# LOCOL_LLM_REQUEST_TIMEOUT, 180s by default - stay above it so a backend
# timeout surfaces as the app's error message rather than as a Playwright one.
LLM_TIMEOUT = int(_env("QA_LLM_TIMEOUT_MS", "240000"))
