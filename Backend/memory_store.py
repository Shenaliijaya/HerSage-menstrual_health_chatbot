# Stores chat history + small session state in memory (for prototype)

_sessions = {}
_session_state = {}  # session_id -> dict (e.g., last_concept)


def get_history(session_id):
    return _sessions.get(session_id, [])


def append_message(session_id, role, content):
    if session_id not in _sessions:
        _sessions[session_id] = []

    _sessions[session_id].append({
        "role": role,
        "content": content
    })


# ---------- NEW: session state helpers ----------
def set_state(session_id: str, key: str, value):
    if session_id not in _session_state:
        _session_state[session_id] = {}
    _session_state[session_id][key] = value


def get_state(session_id: str, key: str, default=None):
    return _session_state.get(session_id, {}).get(key, default)


def set_last_concept(session_id: str, concept_label: str):
    set_state(session_id, "last_concept", concept_label)


def get_last_concept(session_id: str):
    return get_state(session_id, "last_concept", None)


def reset_session(session_id):
    if session_id in _sessions:
        del _sessions[session_id]
    if session_id in _session_state:
        del _session_state[session_id]

