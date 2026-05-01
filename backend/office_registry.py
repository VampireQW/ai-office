"""
Office registry loader for AI办公室.
Keeps employee capabilities and PE workflow ownership outside code.
"""
import json
import os
from functools import lru_cache
from typing import Any, Dict, List


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_PATH = os.path.join(PROJECT_ROOT, "config", "office_registry.json")


@lru_cache(maxsize=1)
def load_office_registry() -> Dict[str, Any]:
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_agent_profile(agent_id: str) -> Dict[str, Any]:
    registry = load_office_registry()
    if agent_id == registry.get("brain", {}).get("id"):
        return registry.get("brain", {})
    return registry.get("agents", {}).get(agent_id, {})


def get_agent_skills(agent_id: str, fallback: List[str]) -> List[str]:
    profile = get_agent_profile(agent_id)
    return profile.get("skills") or fallback
