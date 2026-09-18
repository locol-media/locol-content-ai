"""
Provisioning against the Bifrost LLM gateway's governance API.

When a user registers, their default LLM row is seeded from config/default/llms/llm.yaml
with a shared provider key that talks to Google directly. This module replaces that with
a per-user path through Bifrost: a customer (the "company") and a virtual key hanging
directly off it - then points the user's default LLM row at the gateway using that
virtual key.

The row to fill in is the one named DEFAULT_LLM_MARKER_NAME, which is what the seed
config names it. Both the customer and the key are get-or-create, so this is safe to
run repeatedly: a row that lost its key is repaired with the key the user already has
rather than accumulating a new one.

Gated by LOCOL_BIFROST_ENABLED (see BIFROST_ENABLED below); when off,
provision_default_llm() is a no-op and the seeded config is left exactly as-is. Turning
it off only stops new provisioning - rows already pointing at the gateway keep doing so.
Keys are scoped to the provider and model they're provisioned for, and to that provider's
upstream keys, because Bifrost's governance is deny-by-default at each of those: a scope
left empty permits nothing rather than everything, so a key missing any of the three is
rejected on every call. A key issued before this module scoped them, or scoped only
partly, is widened on its owner's next authenticated request. A virtual key
carries an authorization scope, never provider credentials, so Bifrost itself must also
have a provider entry covering that model for a provisioned user's LLM to work.
"""
import json
import logging
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from db_crypto import encrypt_value, decrypt_or_none

logger = logging.getLogger(__name__)

# Where the gateway lives. Required whenever provisioning is on.
BIFROST_URL = os.environ.get('LOCOL_BIFROST_URL', '').rstrip('/')
# The on/off switch. Unset falls back to whether a URL is configured, which is how this
# was gated before the flag existed, so a deployment still on an older ConfigMap keeps
# behaving as it did - and a local run, which sets neither, stays off. An explicit false
# turns provisioning off even with a URL set; an explicit true without a URL is a
# misconfiguration, reported by _log_skip_once() rather than silently ignored.
_ENABLED_RAW = os.environ.get('LOCOL_BIFROST_ENABLED', '').strip().lower()
BIFROST_ENABLED = bool(BIFROST_URL) and _ENABLED_RAW in ('', 'true', '1', 'yes')
# Only sent if set - Bifrost's governance API is unauthenticated by default.
BIFROST_ADMIN_TOKEN = os.environ.get('LOCOL_BIFROST_ADMIN_TOKEN', '')
BIFROST_TIMEOUT = float(os.environ.get('LOCOL_BIFROST_TIMEOUT', '5'))
# Spend cap put on each new virtual key, in dollars. Empty or non-positive means the
# key is created uncapped.
BIFROST_BUDGET_MAX_LIMIT = os.environ.get('LOCOL_BIFROST_BUDGET_MAX_LIMIT', '')
BIFROST_BUDGET_RESET_DURATION = os.environ.get('LOCOL_BIFROST_BUDGET_RESET_DURATION', '1M')
# What a provisioned row is pointed at, in Bifrost's "<provider>/<model>" form. Nothing
# else names a provider: this string is both what goes on the wire and what the user's
# virtual key is scoped to allow. Deliberately without a default - a deployment names its
# own model, and provisioning is skipped rather than guessing.
BIFROST_DEFAULT_MODEL = os.environ.get('LOCOL_BIFROST_DEFAULT_MODEL', '')
# Seconds to leave a user alone after a failed attempt. Provisioning is retried on every
# authenticated request, so without this a Bifrost outage would add timed-out HTTP calls
# to all of them.
BIFROST_RETRY_INTERVAL = float(os.environ.get('LOCOL_BIFROST_RETRY_INTERVAL', '300'))

# Bifrost's virtual keys are self-identifying, which is what lets us tell a provisioned
# row from a seeded one without storing any extra state.
VK_PREFIX = "sk-bf-"

# Which of a provider's upstream keys a virtual key may draw on. Bifrost denies by default
# here exactly as it does for provider_configs: omitting key_ids, or sending [], selects no
# keys at all, and the call then fails with "no keys found for provider" having already
# passed the provider check. "*" is the documented allow-all, which is what we want - these
# are per-user authorization, not a pin to one upstream credential.
ALL_PROVIDER_KEYS = ["*"]

# The name in config/default/llms/llm.yaml that marks a row as ours to fill in. Keep the
# two in step - a row is only ever provisioned if its name matches this exactly.
DEFAULT_LLM_MARKER_NAME = "Locol AI Default"

# Page size for the list endpoints used by the get-or-create lookups, and a hard cap on
# how far we'll page before giving up.
_PAGE_SIZE = 100
_MAX_PAGES = 20

# Serialises provisioning per user. ensure_user_defaults_seeded() runs on every
# authenticated request and a page load fires several in parallel, which without this
# races them into creating duplicate customers and keys.
_locks_guard = threading.Lock()
_user_locks: dict = {}
_last_failure: dict = {}
# Users whose virtual key has had its provider scope checked in this process. The check
# costs a call to Bifrost and the answer only changes when the key is edited, so doing it
# once per pod lifetime keeps it off the hot path without needing anything persisted.
_scope_checked: set = set()


def _user_lock(user_id: str) -> threading.Lock:
    with _locks_guard:
        return _user_locks.setdefault(user_id, threading.Lock())


def _scope_checked_already(user_id: str) -> bool:
    with _locks_guard:
        return user_id in _scope_checked


def _mark_scope_checked(user_id: str):
    with _locks_guard:
        _scope_checked.add(user_id)


def _in_backoff(user_id: str) -> bool:
    last = _last_failure.get(user_id)
    return last is not None and (time.monotonic() - last) < BIFROST_RETRY_INTERVAL


class BifrostError(Exception):
    """Any failure talking to the Bifrost governance API."""


def _log(message: str, level: int = logging.INFO):
    """
    Report to stdout as well as the logger.

    The BackEnd configures no logging handlers outside llm.py's DEBUG path, and that
    one only runs once an LLM is built - which never happens during registration. A
    logger-only message from here is therefore invisible in container logs, which is
    what makes a silent skip impossible to tell apart from the code never running.
    Everything on this path is once-per-registration, so stdout is cheap.
    """
    print(f"[Bifrost] {message}")
    logger.log(level, f"Bifrost: {message}")


_skip_logged = False


def _log_skip_once():
    """
    Say once per process why provisioning isn't running.

    Unlike the rest of this module, the disabled path is not once-per-registration:
    ensure_user_defaults_seeded() calls provision_default_llm() on every authenticated
    request, so logging per call would put a line in the log for every page load of a
    deployment that doesn't use Bifrost.
    """
    global _skip_logged
    if _skip_logged:
        return
    _skip_logged = True

    if _ENABLED_RAW in ('true', '1', 'yes'):
        _log("LOCOL_BIFROST_ENABLED is on but LOCOL_BIFROST_URL is not set; "
             "leaving default LLMs as seeded", logging.WARNING)
    elif _ENABLED_RAW:
        _log("disabled by LOCOL_BIFROST_ENABLED; leaving default LLMs as seeded")
    else:
        _log("not configured (neither LOCOL_BIFROST_ENABLED nor LOCOL_BIFROST_URL is "
             "set); leaving default LLMs as seeded")


# =============================================================================
# HTTP
# =============================================================================

def _headers():
    headers = {"Content-Type": "application/json"}
    if BIFROST_ADMIN_TOKEN:
        headers["Authorization"] = f"Bearer {BIFROST_ADMIN_TOKEN}"
    return headers


def _safe_body(error: urllib.error.HTTPError) -> str:
    """Read a bounded slice of an error body - it's the only clue to why a create failed."""
    try:
        return error.read()[:300].decode(errors="replace")
    except Exception:
        return "<unreadable>"


def _request(method: str, path: str, payload=None):
    """
    Call the Bifrost API and return the decoded JSON body.

    Response bodies are deliberately never logged: the virtual-key create response
    contains the key itself.
    """
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{BIFROST_URL}{path}",
        data=data,
        headers=_headers(),
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=BIFROST_TIMEOUT) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise BifrostError(f"{method} {path} -> HTTP {e.code}: {_safe_body(e)}") from e
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        raise BifrostError(f"{method} {path} failed: {e}") from e


# =============================================================================
# Response parsing
#
# Bifrost doesn't document the response envelopes for these endpoints, so nothing
# here assumes one. Anything we can't make sense of raises, which leaves the user's
# LLM row untouched rather than writing something broken into it.
# =============================================================================

def _extract_object(payload, *keys) -> dict:
    """Unwrap {"customer": {...}} / {"data": {...}} / a flat {...} alike."""
    if not isinstance(payload, dict):
        raise BifrostError(f"expected a JSON object, got {type(payload).__name__}")
    for key in (*keys, "data", "result"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def _extract_list(payload, *keys) -> list:
    """Unwrap {"customers": [...]} / {"data": [...]} / a bare [...] alike."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in (*keys, "data", "result", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _extract_id(obj: dict, kind: str):
    """
    Pull an entity id out of a response object.

    The value is returned with its original JSON type - ids may be numeric, and
    stringifying one would make the follow-up create fail schema validation.
    """
    for key in ("id", f"{kind}_id", "ID"):
        value = obj.get(key)
        if isinstance(value, (str, int)) and value != "":
            return value
    raise BifrostError(f"no id field in {kind} response")


def _extract_vk_value(payload) -> str:
    """
    Pull the generated virtual key out of a create response, and prove it's one.

    The prefix check is what keeps a changed response envelope from silently
    writing garbage into a user's APIkey column: an unrecognised shape fails here
    instead, and the caller leaves the row as seeded.
    """
    obj = _extract_object(payload, "virtual_key", "virtualKey", "vk")
    for key in ("value", "key", "virtual_key", "vk"):
        value = obj.get(key)
        if isinstance(value, str) and value.startswith(VK_PREFIX):
            return value
    raise BifrostError(f"no '{VK_PREFIX}*' value in virtual-key response")


# =============================================================================
# Governance objects
# =============================================================================

def _find_by_name(path: str, envelope_key: str, name: str, params: dict = None):
    """
    Look an entity up by exact name, paging through the list endpoint.

    Stopping at the first page would start creating duplicates for every existing
    user once an install grows past one page, so page until a short one comes back.
    `params` adds server-side filters (e.g. customer_id) to narrow the scan; the
    name is still matched here rather than via the `search` parameter, whose
    matching semantics aren't documented.
    """
    offset = 0
    for _ in range(_MAX_PAGES):
        query = urllib.parse.urlencode({**(params or {}), "limit": _PAGE_SIZE, "offset": offset})
        items = _extract_list(_request("GET", f"{path}?{query}"), envelope_key)
        for item in items:
            if isinstance(item, dict) and item.get("name") == name:
                return item
        if len(items) < _PAGE_SIZE:
            return None
        offset += _PAGE_SIZE
    _log(f"gave up paging {path} after {_MAX_PAGES} pages looking for '{name}'", logging.WARNING)
    return None


def _ensure_customer(name: str):
    """Get-or-create the customer (the "company") for this user."""
    existing = _find_by_name("/api/governance/customers", "customers", name)
    if existing:
        return _extract_id(existing, "customer")

    try:
        created = _request("POST", "/api/governance/customers", {"name": name})
    except BifrostError:
        # A concurrent create is the likely cause; re-read before giving up.
        existing = _find_by_name("/api/governance/customers", "customers", name)
        if existing:
            return _extract_id(existing, "customer")
        raise
    return _extract_id(_extract_object(created, "customer"), "customer")


def _budgets() -> list:
    """
    The spend cap a new virtual key is created with.

    Returns [] when no budget is configured, which omits the field and leaves the
    key uncapped. Parsed here rather than at import so a typo'd ConfigMap value
    can't break the module - and so it costs an uncapped key rather than a failed
    registration.
    """
    if not BIFROST_BUDGET_MAX_LIMIT:
        return []
    try:
        max_limit = float(BIFROST_BUDGET_MAX_LIMIT)
    except ValueError:
        _log(f"LOCOL_BIFROST_BUDGET_MAX_LIMIT is not a number "
             f"('{BIFROST_BUDGET_MAX_LIMIT}'); creating virtual keys with no budget",
             logging.WARNING)
        return []
    if max_limit <= 0:
        _log(f"LOCOL_BIFROST_BUDGET_MAX_LIMIT is not positive ({max_limit}); "
             f"creating virtual keys with no budget", logging.WARNING)
        return []
    return [{"max_limit": max_limit, "reset_duration": BIFROST_BUDGET_RESET_DURATION}]


def _split_model(model: str):
    """
    Take Bifrost's "<provider>/<model>" apart: "deepseek/deepseek-v4-flash" ->
    ("deepseek", "deepseek-v4-flash").

    Only the first "/" separates the two - some model ids carry further ones. A string
    with no prefix yields (None, model), which every caller reads as "no provider named".
    """
    provider, separator, bare_model = model.partition("/")
    if separator and provider and bare_model:
        return provider, bare_model
    return None, model


def _provider_configs(model: str) -> list:
    """
    The provider scope to put on a virtual key serving `model`.

    Bifrost's governance is deny-by-default at every level here. A key created without
    provider_configs allows no provider at all, and every call through it comes back as
    403 provider_blocked; allowed_models and key_ids deny the same way when left empty,
    so all three have to be stated. allowed_models holds the model without its provider
    prefix, which is the form Bifrost matches once it has resolved the provider.
    """
    provider, bare_model = _split_model(model)
    if not provider:
        _log(f"'{model}' has no '<provider>/' prefix, so a virtual key can't be scoped to "
             f"it; calls through it will be rejected by Bifrost", logging.WARNING)
        return []
    return [{
        "provider": provider,
        "weight": 1.0,
        "allowed_models": [bare_model],
        "key_ids": list(ALL_PROVIDER_KEYS),
    }]


def _ensure_virtual_key(name: str, customer_id, model: str) -> str:
    """
    Reuse this customer's existing key of that name, or mint one, returning its value.

    Bifrost returns key values in full on read, so an existing key is genuinely
    reusable - which is what keeps a row that lost its key (a config resync, a
    hand-edit) from accumulating a new virtual key on every repair. A reused key is
    widened to cover `model` if it doesn't already.
    """
    existing = _find_by_name(
        "/api/governance/virtual-keys", "virtual_keys", name, {"customer_id": customer_id}
    )
    if existing:
        # A match we can't read the value of is not something to paper over by
        # minting a second key under the same name.
        value = _extract_vk_value(existing)
        _log(f"reusing existing virtual key '{name}'")
        _ensure_key_scope(existing, model)
        return value

    return _create_virtual_key(name, customer_id, model)


def _create_virtual_key(name: str, customer_id, model: str) -> str:
    """
    Create a virtual key hanging directly off the customer, and return its value.

    Scoped to the one provider and model it is being provisioned for: Bifrost denies by
    default, so a key created without provider_configs can serve nothing at all.
    """
    payload = {
        "name": name,
        "customer_id": customer_id,
        "is_active": True,
        "provider_configs": _provider_configs(model),
    }
    budgets = _budgets()
    if budgets:
        payload["budgets"] = budgets
    return _extract_vk_value(_request("POST", "/api/governance/virtual-keys", payload))


def _ensure_key_scope(vk_obj: dict, model: str) -> bool:
    """
    Widen an existing virtual key until it can actually serve `model`. Returns True if a
    change was written.

    There are two ways a key gets stuck, and both fail after provisioning has reported
    success: one with no provider_configs at all, which Bifrost reads as "no provider
    allowed" and answers with 403 provider_blocked; one naming the provider and model but
    no key_ids, which passes that check and then matches none of the provider's upstream
    keys, giving "no keys found for provider". So both fields are checked, not just the
    model.

    The merge is done here rather than by PUTting our own entry alone because the
    provider_configs array is replaced wholesale: a blind write would drop the entries for
    any other provider, along with the server-assigned ids and budgets they carry. Only
    empty fields are filled in - a deliberate pin to specific key ids is left alone.
    Adding to an entry whose allowed_models is empty narrows a key that Bifrost's admin UI
    would describe as unrestricted, but an empty list is what the API denies on, so a key
    in that state is failing already.
    """
    provider, bare_model = _split_model(model)
    if not provider:
        return False

    raw = vk_obj.get("provider_configs")
    configs = [c for c in raw if isinstance(c, dict)] if isinstance(raw, list) else []

    merged = []
    matched = False
    widened = []
    for config in configs:
        if config.get("provider") != provider:
            merged.append(config)
            continue
        matched = True
        allowed = config.get("allowed_models")
        allowed = list(allowed) if isinstance(allowed, list) else []
        key_ids = config.get("key_ids")
        key_ids = list(key_ids) if isinstance(key_ids, list) else []
        if bare_model in allowed and key_ids:
            return False

        updated = {**config}
        if bare_model not in allowed:
            updated["allowed_models"] = allowed + [bare_model]
            widened.append(f"model {model}")
        if not key_ids:
            updated["key_ids"] = list(ALL_PROVIDER_KEYS)
            widened.append(f"all of {provider}'s keys")
        merged.append(updated)

    if not matched:
        scope = _provider_configs(model)
        if not scope:
            return False
        merged = configs + scope
        widened.append(f"model {model}")

    _request("PUT", f"/api/governance/virtual-keys/{_extract_id(vk_obj, 'virtual_key')}",
             {"provider_configs": merged})
    _log(f"widened virtual key '{vk_obj.get('name')}' to allow {' and '.join(widened)}")
    return True


# =============================================================================
# Entry point
# =============================================================================

def _read_default_llm(user_db_path: str):
    """
    Find the row marked as ours to fill in, by name.

    Returns (id, APIkey, model) or None. The marker name is the whole test: a row
    called DEFAULT_LLM_MARKER_NAME is app-managed by definition, so unlike an
    id-based or position-based guess this can never pick up an LLM the user
    configured themselves.
    """
    conn = sqlite3.connect(user_db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, APIkey, model FROM llms WHERE name = ?", (DEFAULT_LLM_MARKER_NAME,)
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        _log(f"no LLM named '{DEFAULT_LLM_MARKER_NAME}' to provision")
        return None
    if len(rows) > 1:
        _log(f"{len(rows)} LLMs named '{DEFAULT_LLM_MARKER_NAME}'; using '{rows[0][0]}'",
             logging.WARNING)
    return rows[0]


def _resolve_model(row_model: str):
    """
    The model a provisioned row is pointed at.

    Config wins so the choice can be changed per environment without a rebuild;
    the row's own model is the fallback, which keeps a `model:` in llm.yaml
    working. Returns None if there's nothing usable - better to leave the row
    alone than to point it at a model Bifrost can't route.
    """
    model = BIFROST_DEFAULT_MODEL or row_model
    if not model:
        _log("no model configured (LOCOL_BIFROST_DEFAULT_MODEL) and none on the row",
             logging.WARNING)
        return None
    return model


def _write_default_llm(user_db_path: str, llm_id: str, vk_value: str, api_url: str, model: str):
    """
    Point the default LLM row at Bifrost.

    APIstyle becomes "openai" because that's the only branch of LLM._build_model()
    that honours APIurl as a base_url, and Bifrost speaks the OpenAI protocol.
    Written as one statement so the row can never be left half-provisioned.
    """
    conn = sqlite3.connect(user_db_path)
    try:
        conn.execute(
            "UPDATE llms SET APIkey = ?, APIstyle = 'openai', APIurl = ?, model = ? WHERE id = ?",
            (encrypt_value(vk_value), api_url, model, llm_id),
        )
        conn.commit()
    finally:
        conn.close()


def _needs_provisioning(row) -> bool:
    """
    True if the marker row is still waiting for a virtual key.

    A key that can't be decrypted counts as needing one: it isn't a value we can
    confirm as ours, and it can never be used to call anything again. Provisioning
    then overwrites it, which repairs the row rather than losing anything - the
    value was already unrecoverable - and is how a default row survives the
    encryption key being replaced.
    """
    llm_id, stored_key, _ = row
    plaintext = decrypt_or_none(stored_key)
    return not (plaintext and plaintext.startswith(VK_PREFIX))


def _repair_key_scope(user_id: str, row, username: str = None) -> bool:
    """
    Widen an already-provisioned user's virtual key to cover the model on their row.

    Nothing else revisits a row that already holds a key, so a user whose key predates
    provider scoping would go on getting a 403 provider_blocked on every generation
    forever. Checked once per process per user, since this sits on the path of every
    authenticated request and the answer only changes if the key is edited in Bifrost.

    Scoped to the row's own model rather than LOCOL_BIFROST_DEFAULT_MODEL: the row is
    what llm.py actually puts on the wire, and repairing a working user is not the place
    to move them onto a model the deployment has since switched to.

    Always returns True - the row does point at Bifrost, which is what the caller asked,
    and a gateway that can't be reached must not fail a sign-in.
    """
    if _scope_checked_already(user_id) or _in_backoff(user_id):
        return True

    try:
        with _user_lock(user_id):
            if _scope_checked_already(user_id):
                return True

            _llm_id, _stored_key, row_model = row
            if not _split_model(row_model or "")[0]:
                # No provider named, so there is no scope to check against.
                _mark_scope_checked(user_id)
                return True

            if not username:
                from user_management import get_user_by_id
                user = get_user_by_id(user_id)
                if not user:
                    _log(f"no user record for {user_id}; can't check its virtual key scope",
                         logging.WARNING)
                    return True
                username = user["username"]

            vk_name = f"{username}-key"
            existing = _find_by_name("/api/governance/virtual-keys", "virtual_keys", vk_name)
            if existing is None:
                _log(f"no virtual key named '{vk_name}' in Bifrost, but user {user_id} holds "
                     f"one; its scope can't be checked", logging.WARNING)
            else:
                _ensure_key_scope(existing, row_model)
            _mark_scope_checked(user_id)

    except Exception as e:
        _last_failure[user_id] = time.monotonic()
        _log(f"couldn't check the virtual key scope for user {user_id}: {e}; retrying in at "
             f"most {int(BIFROST_RETRY_INTERVAL)}s", logging.WARNING)

    return True


def provision_default_llm(user_id: str, username: str = None) -> bool:
    """
    Give this user's "Locol AI Default" LLM a Bifrost virtual key, creating the
    customer and key if they don't exist yet and reusing them if they do, then
    point the row at the gateway.

    Safe to call on every authenticated request: once the row holds a key this costs
    one SELECT, plus a single check per process that the key's provider scope still
    covers the row's model. Never raises - on any failure it logs a warning and leaves
    the row as seeded, so registration still succeeds.

    `username` may be omitted, in which case it's looked up - but only once the
    row actually needs work, since that lookup is not free.

    Returns True if the row points at Bifrost, False if provisioning was skipped
    (feature disabled, no marker row, nothing configured) or failed. Note that a
    False from the disabled check says nothing about rows provisioned earlier -
    turning the feature off leaves those pointing at the gateway.
    """
    if not BIFROST_ENABLED:
        _log_skip_once()
        return False

    try:
        from db_manager import get_user_db_path
        user_db_path = get_user_db_path(user_id)

        row = _read_default_llm(user_db_path)
        if row is None:
            return False
        if not _needs_provisioning(row):
            return _repair_key_scope(user_id, row, username)
        if _in_backoff(user_id):
            return False

        with _user_lock(user_id):
            # Another thread may have provisioned this user while we waited.
            row = _read_default_llm(user_db_path)
            if row is None:
                return False
            if not _needs_provisioning(row):
                return True

            llm_id, _stored_key, row_model = row
            bifrost_model = _resolve_model(row_model)
            if bifrost_model is None:
                return False

            if not username:
                from user_management import get_user_by_id
                user = get_user_by_id(user_id)
                if not user:
                    _log(f"no user record for {user_id}; can't name the Bifrost customer",
                         logging.WARNING)
                    return False
                username = user["username"]

            _log(f"provisioning user {user_id} ('{username}') against {BIFROST_URL}")
            customer_id = _ensure_customer(username)
            vk_name = f"{username}-key"
            vk_value = _ensure_virtual_key(vk_name, customer_id, bifrost_model)

            try:
                _write_default_llm(user_db_path, llm_id, vk_value, f"{BIFROST_URL}/v1", bifrost_model)
            except sqlite3.Error:
                # The key exists in Bifrost but nothing references it. Name it (never
                # its value) so it can be found by hand. The next attempt reuses it
                # rather than minting another.
                _log(f"virtual key '{vk_name}' not stored - it will be reused on retry",
                     logging.WARNING)
                raise

            _last_failure.pop(user_id, None)
            # The key was just scoped to this model, so the next request needn't ask.
            _mark_scope_checked(user_id)
            _log(f"provisioned customer '{username}' and virtual key '{vk_name}' for user "
                 f"{user_id}; LLM '{llm_id}' now points at {BIFROST_URL}/v1 as {bifrost_model}")
            return True

    except Exception as e:
        _last_failure[user_id] = time.monotonic()
        _log(f"provisioning failed for user {user_id}: {e}; retrying in at most "
             f"{int(BIFROST_RETRY_INTERVAL)}s", logging.WARNING)
        return False
