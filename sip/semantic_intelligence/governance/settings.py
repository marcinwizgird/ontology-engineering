"""Scoped settings — Semantic Turkey's ``STPropertiesManager``.

Five scopes (``Scope.java``): ``sys``, ``proj``, ``usr``, ``pu`` (project-user)
and ``pg`` (project-group). Resolution is a layered merge, later layers override
earlier ones:

* ``pu``   : system default → user default → project default → pg (user's group) → pu
* ``proj`` : project default@system → project
* ``usr``  : user default@system → user
* ``sys``  : the system layer only

Settings are plain dicts keyed by *component* (``"rendering"``, ``"urigen"``,
``"agents"``…). Semantic Turkey persists YAML files per scope; here the store is a
dict so that it can be serialised wherever the deployment keeps configuration.
"""

from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any

SCOPES = ("sys", "proj", "usr", "pu", "pg")


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


class SettingsStore:
    def __init__(self) -> None:
        # (component, scope, key) -> dict ; key identifies the layer instance
        self._layers: dict[tuple[str, str, tuple], dict[str, Any]] = defaultdict(dict)

    def store(self, component: str, scope: str, values: dict[str, Any], *,
              project: str | None = None, user: str | None = None,
              group: str | None = None, default_of: str | None = None) -> None:
        """Write one layer. ``default_of`` stores the *defaults* a scope keeps for a
        narrower scope (e.g. ``scope="sys", default_of="pu"`` = PU defaults at system)."""
        if scope not in SCOPES:
            raise ValueError(f"scope must be one of {SCOPES}")
        key = (component, scope, (project, user, group, default_of))
        self._layers[key] = _merge(self._layers.get(key, {}), values)

    def _get(self, component, scope, project=None, user=None, group=None, default_of=None):
        return self._layers.get((component, scope, (project, user, group, default_of)), {})

    def get(self, component: str, scope: str, *, project: str | None = None,
            user: str | None = None, group: str | None = None,
            explicit: bool = False) -> dict[str, Any]:
        if explicit:
            return copy.deepcopy(self._get(component, scope, project, user, group))
        if scope == "sys":
            chain = [self._get(component, "sys")]
        elif scope == "proj":
            chain = [self._get(component, "sys", default_of="proj"),
                     self._get(component, "proj", project=project)]
        elif scope == "usr":
            chain = [self._get(component, "sys", default_of="usr"),
                     self._get(component, "usr", user=user)]
        elif scope == "pu":
            chain = [self._get(component, "sys", default_of="pu"),
                     self._get(component, "usr", user=user, default_of="pu"),
                     self._get(component, "proj", project=project, default_of="pu")]
            if group:
                chain.append(self._get(component, "pg", project=project, group=group))
            chain.append(self._get(component, "pu", project=project, user=user))
        elif scope == "pg":
            chain = [self._get(component, "pg", project=project, group=group)]
        else:
            raise ValueError(f"scope must be one of {SCOPES}")
        out: dict[str, Any] = {}
        for layer in chain:
            out = _merge(out, layer)
        return out
