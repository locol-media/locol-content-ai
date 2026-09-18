import os
import streamlit as st

# Local runs put BackEnd on localhost, so its port is all that's needed to reach it -
# following LOCOL_BACKEND_PORT here means moving the BackEnd off 8000 doesn't silently
# leave the Web app talking to nothing. Deployments set both URLs below explicitly
# (see k8s/01-configmap.yaml), where this default never comes into play.
_LOCAL_BACKEND = f"http://localhost:{os.environ.get('LOCOL_BACKEND_PORT', '8000')}"

LOCOL_API_URL = os.environ.get('LOCOL_API_URL', _LOCAL_BACKEND)
LOCOL_WWW_URL = os.environ.get('LOCOL_WWW_URL', _LOCAL_BACKEND)

# Seconds to wait on any request that triggers an LLM call. Model latency is
# measured in minutes, not seconds - plain CRUD calls keep their own short
# timeouts so an unreachable backend still fails fast on ordinary page loads.
# Keep the ingress proxy-read-timeout (k8s/05-ingress.yaml) above this, or
# nginx 504s first and the app's own timeout message never gets shown.
LLM_REQUEST_TIMEOUT = int(os.environ.get('LOCOL_LLM_REQUEST_TIMEOUT', '180'))

# Human-readable form of the above, for "timed out after ..." messages - so
# they can't drift out of sync with the value the way hardcoded prose did.
def _describe_timeout(seconds):
    if seconds >= 60 and seconds % 60 == 0:
        minutes = seconds // 60
        return f"{minutes} minute{'' if minutes == 1 else 's'}"
    return f"{seconds} second{'' if seconds == 1 else 's'}"


LLM_TIMEOUT_DESCRIPTION = _describe_timeout(LLM_REQUEST_TIMEOUT)

# Whether the Reddit writing-style analyser on the Find Your Voice page is offered.
# Off by default: Reddit blocks the automated access it depends on (see
# BackEnd/src/find_your_voice.py). BackEnd reads the same variable and refuses the
# request on its own, so the two must be set to the same value or the form is offered
# and then answered with "unavailable".
FIND_YOUR_VOICE_ENABLED = os.environ.get('LOCOL_FIND_YOUR_VOICE_ENABLED', '').lower() in ('true', '1', 'yes')


def get_api_headers():
    """Get headers with JWT token for API calls"""
    headers = {"Content-Type": "application/json"}
    if hasattr(st.session_state, 'jwt_token') and st.session_state.jwt_token:
        headers["Authorization"] = f"Bearer {st.session_state.jwt_token}"
    return headers
