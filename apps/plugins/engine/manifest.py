from __future__ import annotations

from dataclasses import dataclass

from apps.plugins.engine.exceptions import PluginManifestError


@dataclass(slots=True)
class ManifestDependency:
    slug: str
    min_version: str = ""


@dataclass(slots=True)
class PluginManifest:
    slug: str
    name: str
    version: str
    entrypoint: str
    scopes: list[str]
    dependencies: list[ManifestDependency]
    config_schema: dict
    default_config: dict
    core_version_min: str
    core_version_max: str
    env_vars: dict


def parse_manifest(raw: dict) -> PluginManifest:
    slug = str(raw.get("slug") or "").strip()
    name = str(raw.get("name") or "").strip()
    version = str(raw.get("version") or "").strip()
    entrypoint = str(raw.get("entrypoint") or "entrypoint.py").strip()
    if not slug or not name or not version:
        raise PluginManifestError("Manifest must include slug, name and version.")

    scopes = [str(scope).strip() for scope in (raw.get("scopes") or []) if str(scope).strip()]

    dependencies_raw = raw.get("dependencies") or []
    dependencies: list[ManifestDependency] = []
    for dep in dependencies_raw:
        if isinstance(dep, str):
            dep_slug = dep.strip()
            if dep_slug:
                dependencies.append(ManifestDependency(slug=dep_slug))
            continue
        if isinstance(dep, dict):
            dep_slug = str(dep.get("slug") or "").strip()
            if dep_slug:
                dependencies.append(
                    ManifestDependency(slug=dep_slug, min_version=str(dep.get("min_version") or "").strip())
                )

    config_schema = raw.get("config_schema") or {}
    if not isinstance(config_schema, dict):
        raise PluginManifestError("config_schema must be an object.")

    default_config = raw.get("default_config") or {}
    if not isinstance(default_config, dict):
        raise PluginManifestError("default_config must be an object.")

    env_vars_raw = raw.get("env_vars") or {}
    if not isinstance(env_vars_raw, dict):
        raise PluginManifestError("env_vars must be an object mapping config keys to environment variable names.")
    env_vars = {str(k).strip(): str(v).strip() for k, v in env_vars_raw.items() if str(k).strip() and str(v).strip()}

    return PluginManifest(
        slug=slug,
        name=name,
        version=version,
        entrypoint=entrypoint,
        scopes=scopes,
        dependencies=dependencies,
        config_schema=config_schema,
        default_config=default_config,
        core_version_min=str(raw.get("core_version_min") or "").strip(),
        core_version_max=str(raw.get("core_version_max") or "").strip(),
        env_vars=env_vars,
    )
