from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from app.task_types import TASK_GUIDED_UI_TASK, extract_message_body

SITE_TERMS = ("bilibili", "youtube", "wikipedia", "amazon", "github", "reddit", "facebook")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _candidate_text(candidate: Dict[str, Any]) -> str:
    return " ".join(
        _lower(candidate.get(key))
        for key in ("label", "resource_id", "content_desc", "class_name", "hint")
    )


def _screen_corpus(screen_summary: Dict[str, Any]) -> str:
    fragments = [_lower(item) for item in screen_summary.get("visible_text", [])]
    for candidate in screen_summary.get("possible_targets", []):
        if isinstance(candidate, dict):
            fragments.append(_candidate_text(candidate))
    return " ".join(fragment for fragment in fragments if fragment)


def _find_clickable_target(
    screen_summary: Dict[str, Any],
    labels: Sequence[str],
) -> Optional[Dict[str, Any]]:
    wanted = [_lower(label) for label in labels if _text(label)]
    for candidate in screen_summary.get("possible_targets", []):
        if not isinstance(candidate, dict) or not bool(candidate.get("clickable")):
            continue
        combined = _candidate_text(candidate)
        if any(label == combined or label in combined for label in wanted):
            return candidate
    return None


def _find_primary_input(screen_summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    best: Optional[Dict[str, Any]] = None
    best_score = -1
    for candidate in screen_summary.get("possible_targets", []):
        if not isinstance(candidate, dict):
            continue
        class_name = _lower(candidate.get("class_name"))
        if "edittext" not in class_name:
            continue
        score = 0
        if bool(candidate.get("focused")):
            score += 4
        if bool(candidate.get("clickable")):
            score += 1
        combined = _candidate_text(candidate)
        if any(marker in combined for marker in ("search", "url", "query", "address", "find")):
            score += 2
        if score > best_score:
            best_score = score
            best = candidate
    return best


def _action_from_candidate(skill: str, candidate: Dict[str, Any]) -> Dict[str, Any]:
    target = candidate.get("label") or candidate.get("content_desc") or candidate.get("resource_id") or ""
    args: Dict[str, Any] = {"target": target}
    target_id = _text(candidate.get("target_id"))
    if target_id:
        args["target_id"] = target_id
        args["action_id"] = "{0}:{1}".format(skill, target_id)
    return {"skill": skill, "args": args}


def _looks_like_stylus_overlay(corpus: str) -> bool:
    strong_markers = (
        "try out your stylus",
        "write here",
        "use your stylus",
        "handwriting is automatically converted to text",
        "stylus",
    )
    if not any(marker in corpus for marker in strong_markers):
        return False
    controls = ("cancel", "next", "reset", "write", "delete", "select", "insert")
    return sum(1 for marker in controls if marker in corpus) >= 2


def _permission_blocker(screen_summary: Dict[str, Any], corpus: str) -> Optional[Dict[str, Any]]:
    if not any(marker in corpus for marker in ("allow", "don\u2019t allow", "don't allow", "permission")):
        return None
    if not any(marker in corpus for marker in ("send you notifications", "access", "permission")):
        return None
    target = _find_clickable_target(screen_summary, ("Allow", "While using the app", "Only this time"))
    if not target:
        return None
    return {
        "type": "permission_dialog",
        "severity": "blocking",
        "reason": "A permission dialog is blocking the target app.",
        "suggested_action": _action_from_candidate("tap", target),
    }


def _onboarding_blocker(screen_summary: Dict[str, Any], corpus: str) -> Optional[Dict[str, Any]]:
    markers = (
        "take me to gmail",
        "got it",
        "not now",
        "skip",
        "welcome",
        "set up email",
        "google meet, now in gmail",
        "try another way",
    )
    if not any(marker in corpus for marker in markers):
        return None
    target = _find_clickable_target(
        screen_summary,
        (
            "TAKE ME TO GMAIL",
            "Got it",
            "Close",
            "Not now",
            "Skip",
            "Next",
            "Continue",
        ),
    )
    if not target:
        return None
    return {
        "type": "onboarding_dialog",
        "severity": "blocking",
        "reason": "An onboarding or setup surface must be dismissed before the task can continue.",
        "suggested_action": _action_from_candidate("tap", target),
    }


def _system_overlay_blocker(screen_summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    overlay = screen_summary.get("system_overlay")
    if not isinstance(overlay, dict):
        return None
    if not overlay.get("present") or not overlay.get("blocks_input"):
        return None
    overlay_type = _text(overlay.get("type")) or "system_overlay"
    recovery = _text(overlay.get("recommended_recovery")) or "back"
    skill = "back" if recovery in ("back", "none") else recovery
    evidence = overlay.get("evidence") if isinstance(overlay.get("evidence"), list) else []
    reason = "A system-level overlay is covering or intercepting the target app."
    if "input_method" in overlay_type:
        reason = "A system input-method overlay is covering or intercepting the focused input."
    return {
        "type": "system_{0}".format(overlay_type),
        "severity": "blocking",
        "reason": reason,
        "suggested_action": {"skill": skill, "args": {}},
        "source": "system_overlay",
        "confidence": overlay.get("confidence", 0.0),
        "evidence": evidence[:5],
    }


def detect_blockers(screen_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    corpus = _screen_corpus(screen_summary)
    blockers: List[Dict[str, Any]] = []
    if _looks_like_stylus_overlay(corpus):
        blockers.append(
            {
                "type": "input_blocking_overlay",
                "severity": "blocking",
                "reason": "A stylus or handwriting overlay is covering the focused input.",
                "suggested_action": {"skill": "back", "args": {}},
            }
        )
    system_overlay = _system_overlay_blocker(screen_summary)
    if system_overlay:
        blockers.append(system_overlay)
    permission = _permission_blocker(screen_summary, corpus)
    if permission:
        blockers.append(permission)
    onboarding = _onboarding_blocker(screen_summary, corpus)
    if onboarding:
        blockers.append(onboarding)
    return blockers


def _goal_looks_search(goal: str) -> bool:
    normalized = _lower(goal)
    return any(
        marker in normalized
        for marker in ("search ", "search for", "find ", "find videos", "find video", "look up", "look for")
    )


def _extract_search_query(goal: str) -> str:
    quoted = extract_message_body(goal)
    if quoted:
        return quoted
    normalized = _lower(goal)
    patterns = (
        r"(?:find|look\s+for|look\s+up|search(?:\s+for)?)(?:\s+videos?)?(?:\s+about|\s+for)?\s+(.+)",
        r"(?:videos?\s+about)\s+(.+)",
    )
    query = ""
    for pattern in patterns:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            query = match.group(1).strip(" .,!?:;")
            break
    if not query:
        return ""
    query = re.sub(r"^(on|in|with)\s+", "", query).strip()
    query = re.sub(r"\s+(on|in)\s+(chrome|browser|web)\b.*$", "", query).strip()
    for site in SITE_TERMS:
        if site in normalized and site not in query:
            return "{0} {1}".format(site, query).strip()[:120]
    return query[:120]


def _query_tokens(goal: str) -> List[str]:
    query = _extract_search_query(goal)
    return [token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) >= 2]


def _content_query_tokens(goal: str) -> List[str]:
    tokens = _query_tokens(goal)
    content_tokens = [token for token in tokens if token not in SITE_TERMS and token not in {"video", "videos"}]
    return content_tokens or tokens


def _requested_site_terms(goal: str) -> List[str]:
    normalized_goal = _lower(goal)
    return [term for term in SITE_TERMS if term in normalized_goal]


def _search_goal_complete(goal: str, screen_summary: Dict[str, Any], corpus: str) -> bool:
    query_tokens = _query_tokens(goal)
    required_tokens = _content_query_tokens(goal)
    current_url = _lower(screen_summary.get("current_url"))
    current_domain = _lower(screen_summary.get("current_domain"))
    requested_sites = _requested_site_terms(goal)

    def has_requested_site_evidence() -> bool:
        if not requested_sites:
            return True
        return any(term in current_domain or term in current_url or term in corpus for term in requested_sites)

    if required_tokens and any(token in current_url for token in required_tokens) and (
        "/search" in current_url or "keyword=" in current_url or "q=" in current_url
    ):
        if any(term in current_domain for term in requested_sites):
            return True
        if not requested_sites:
            return True
    query_hits = sum(1 for token in required_tokens if token in corpus)
    if not required_tokens or query_hits < max(1, min(2, len(required_tokens))):
        return False
    if not has_requested_site_evidence():
        return False
    return "search?keyword=" in corpus or "search result" in corpus or "search results" in corpus


def assess_goal_progress(
    goal: str,
    task_type: str,
    screen_summary: Dict[str, Any],
    blockers: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    corpus = _screen_corpus(screen_summary)
    page = _lower(screen_summary.get("page"))
    app = _lower(screen_summary.get("app"))
    blockers = blockers or []

    if task_type != TASK_GUIDED_UI_TASK:
        return {"stage": "unknown", "status": "not_applicable", "done": False, "next_hint": ""}

    if blockers:
        return {
            "stage": "clear_blocker",
            "status": "blocked",
            "done": False,
            "next_hint": blockers[0].get("reason", "Clear the blocking UI first."),
        }

    normalized_goal = _lower(goal)
    if "gmail" in normalized_goal and ("draft" in normalized_goal or "email" in normalized_goal):
        if all(marker in corpus for marker in ("send", "from")) and "compose" in corpus:
            return {
                "stage": "done",
                "status": "complete",
                "done": True,
                "next_hint": "Compose editor is visible; do not tap Send for a draft-only task.",
            }
        if "com.google.android.gm" not in app:
            return {"stage": "open_app", "status": "in_progress", "done": False, "next_hint": "Open Gmail."}
        if "compose" in corpus:
            return {"stage": "start_draft", "status": "ready", "done": False, "next_hint": "Tap Compose."}
        return {"stage": "navigate_home", "status": "in_progress", "done": False, "next_hint": "Reach Gmail inbox."}

    if _goal_looks_search(goal):
        if _search_goal_complete(goal, screen_summary, corpus):
            return {
                "stage": "done",
                "status": "complete",
                "done": True,
                "next_hint": "Search result state is visible.",
            }
        primary_input = _find_primary_input(screen_summary)
        if primary_input:
            return {
                "stage": "enter_query",
                "status": "ready",
                "done": False,
                "next_hint": "Enter or submit search query: {0}".format(_extract_search_query(goal)),
            }
        if page.endswith("site") or page == "browser_site":
            return {
                "stage": "find_site_search",
                "status": "in_progress",
                "done": False,
                "next_hint": "Find the site search control.",
            }
        return {"stage": "open_search_surface", "status": "in_progress", "done": False, "next_hint": "Open search UI."}

    if "keep" in normalized_goal and ("note" in normalized_goal or "create" in normalized_goal):
        if page == "keep_editor":
            quoted = extract_message_body(goal)
            return {
                "stage": "fill_note" if quoted else "done",
                "status": "ready" if quoted else "complete",
                "done": not bool(quoted),
                "next_hint": "Type requested note text." if quoted else "Keep editor is open.",
            }
        return {"stage": "open_editor", "status": "in_progress", "done": False, "next_hint": "Open a new Keep note."}

    return {"stage": "unknown", "status": "unknown", "done": False, "next_hint": ""}


def normalize_ui_state(
    goal: str,
    task_type: str,
    screen_summary: Dict[str, Any],
    recent_actions: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    primary_input = _find_primary_input(screen_summary)
    blockers = detect_blockers(screen_summary)
    input_context = None
    if primary_input and task_type == TASK_GUIDED_UI_TASK and _goal_looks_search(goal):
        input_overlay_types = ("input_blocking_overlay", "system_handwriting_input_method", "system_input_method")
        input_context_blockers = [
            blocker
            for blocker in blockers
            if isinstance(blocker, dict) and _text(blocker.get("type")) in input_overlay_types
        ]
        if input_context_blockers:
            input_context = {
                "type": "input_method_overlay",
                "status": "active",
                "reason": "Input-method UI is present, but a search input is available; continue entering the query.",
                "suppressed_blockers": input_context_blockers,
            }
            blockers = [
                blocker
                for blocker in blockers
                if not (isinstance(blocker, dict) and _text(blocker.get("type")) in input_overlay_types)
            ]
    progress = assess_goal_progress(goal, task_type, screen_summary, blockers=blockers)
    return {
        "app": screen_summary.get("app"),
        "page": screen_summary.get("page"),
        "current_url": screen_summary.get("current_url"),
        "current_domain": screen_summary.get("current_domain"),
        "blockers": blockers,
        "primary_blocker": blockers[0] if blockers else None,
        "primary_input": {
            "label": primary_input.get("label"),
            "target_id": primary_input.get("target_id"),
            "resource_id": primary_input.get("resource_id"),
            "focused": bool(primary_input.get("focused")),
        }
        if primary_input
        else None,
        "input_context": input_context,
        "goal_progress": progress,
        "recent_action_count": len(list(recent_actions or [])),
    }
