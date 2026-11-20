from pathlib import Path
from typing import Optional
from backend.app.core.config import settings

def sanitize_filesystem_path(path_str: Optional[str]) -> Optional[str]:
    """
    Sanitizes absolute filesystem paths to safe relative paths or names.
    Prevents leakage of host usernames, directory structures, and worker mounts.
    """
    if not path_str:
        return None
    p = str(path_str).strip()
    if not p:
        return None

    # Check workspace containment
    try:
        ws_str = str(settings.WORKSPACE_DIR.resolve())
        resolved = str(Path(p).resolve())
        if resolved.startswith(ws_str):
            rel = resolved[len(ws_str):].lstrip("/\\")
            return rel or "."
    except Exception:
        pass

    try:
        ws_str = str(settings.WORKSPACE_DIR)
        if p.startswith(ws_str):
            rel = p[len(ws_str):].lstrip("/\\")
            return rel or "."
    except Exception:
        pass

    # Check home directory containment
    try:
        home_str = str(Path.home())
        if p.startswith(home_str):
            return f"~{p[len(home_str):]}"
    except Exception:
        pass

    # Kane worker internal session or container paths
    if "/.testmuai/" in p or "/sessions/" in p:
        return Path(p).name

    # If it is an absolute path on macOS or Linux
    if p.startswith(("/Users/", "/home/", "/var/", "/private/", "/tmp/")):
        return Path(p).name

    return p

def sanitize_kane_session_id(session_str: Optional[str]) -> Optional[str]:
    """
    Transforms internal container/host session paths (e.g. /home/kane/.testmuai/kaneai/sessions/<uuid>)
    into just the safe session UUID identifier.
    """
    if not session_str:
        return None
    s = str(session_str).strip()
    if "/" in s or "\\" in s:
        return Path(s).name
    return s

def sanitize_user_identifier(user_id: Optional[str]) -> Optional[str]:
    """
    Sanitizes host system usernames or internal identities into safe, readable roles.
    """
    if not user_id:
        return None
    u = str(user_id).strip()
    u_lower = u.lower()
    if "auditor" in u_lower:
        return "Principal Security Auditor"
    if "operator" in u_lower or "admin" in u_lower:
        return "Authorized Operator"
    if "reviewer" in u_lower:
        return "Authorized Reviewer"
    # If it contains a hyphen like "pratham-principal-auditor" or similar
    if "-" in u:
        parts = u.split("-")
        return f"Authorized Operator ({parts[0]})"
    return "Authorized Reviewer"
