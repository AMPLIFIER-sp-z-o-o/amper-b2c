from __future__ import annotations

import importlib.util
import inspect
import re
import tempfile
import traceback
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.plugins.engine.exceptions import PluginAbortAction, PluginManifestError
from apps.plugins.engine.lifecycle import _resolve_zip_plugin_root, _safe_extract_zip, load_manifest_from_directory
from apps.plugins.engine.manifest import PluginManifest

KNOWN_SCOPES = {"data:write", "http:outbound", "payments:write"}
KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ENV_VAR_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
REGISTERED_HOOK_RE = re.compile(r"api\.register_(?:filter|action|async_action)\(\s*[\"']([^\"']+)[\"']")
SCOPE_USAGE_PATTERNS = {
    "http:outbound": re.compile(r"\bapi\.http\."),
    "data:write": re.compile(r"\bapi\.data\.(?:set|delete)\s*\("),
    "payments:write": re.compile(r"\bensure_plugin_payment_method\s*\("),
}


@dataclass(slots=True)
class ValidationMessage:
    level: str
    code: str
    message: str
    hint: str = ""

    def as_lines(self) -> list[str]:
        lines = [f"[{self.level}] {self.code}: {self.message}"]
        if self.hint:
            lines.append(f"      Fix: {self.hint}")
        return lines


@dataclass(slots=True)
class ZipValidationReport:
    archive_path: Path
    plugin_root: Path | None = None
    manifest: PluginManifest | None = None
    messages: list[ValidationMessage] = field(default_factory=list)

    def add_error(self, code: str, message: str, *, hint: str = "") -> None:
        self.messages.append(ValidationMessage(level="ERROR", code=code, message=message, hint=hint))

    def add_warning(self, code: str, message: str, *, hint: str = "") -> None:
        self.messages.append(ValidationMessage(level="WARNING", code=code, message=message, hint=hint))

    def add_info(self, code: str, message: str, *, hint: str = "") -> None:
        self.messages.append(ValidationMessage(level="INFO", code=code, message=message, hint=hint))

    @property
    def errors(self) -> list[ValidationMessage]:
        return [message for message in self.messages if message.level == "ERROR"]

    @property
    def warnings(self) -> list[ValidationMessage]:
        return [message for message in self.messages if message.level == "WARNING"]

    @property
    def infos(self) -> list[ValidationMessage]:
        return [message for message in self.messages if message.level == "INFO"]

    @property
    def has_blocking_errors(self) -> bool:
        return bool(self.errors)


class _DryRunDataAPI:
    def __init__(self, scopes: set[str]) -> None:
        self._scopes = scopes

    def get(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        return default

    def set(self, key: str, value: Any, namespace: str = "default") -> None:
        if "data:write" not in self._scopes:
            raise RuntimeError("Scope 'data:write' is required for api.data.set().")

    def delete(self, key: str, namespace: str = "default") -> None:
        if "data:write" not in self._scopes:
            raise RuntimeError("Scope 'data:write' is required for api.data.delete().")

    def list_namespace(self, namespace: str = "default") -> dict[str, Any]:
        return {}


class _DryRunHTTPAPI:
    def __init__(self, scopes: set[str]) -> None:
        self._scopes = scopes

    def get(self, url: str, *, headers: dict[str, str] | None = None, timeout_seconds: float = 4.0) -> dict[str, Any]:
        return self.request("GET", url, headers=headers, timeout_seconds=timeout_seconds)

    def post(
        self,
        url: str,
        *,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 4.0,
    ) -> dict[str, Any]:
        return self.request("POST", url, body=body, headers=headers, timeout_seconds=timeout_seconds)

    def request(
        self,
        method: str,
        url: str,
        *,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 4.0,
    ) -> dict[str, Any]:
        if "http:outbound" not in self._scopes:
            raise RuntimeError("Scope 'http:outbound' is required for api.http.request().")
        _ = method, url, body, headers, timeout_seconds
        return {"ok": True, "status_code": 200, "data": {"dry_run": True}}


class _DryRunPluginAPI:
    AbortAction = PluginAbortAction

    def __init__(self, scopes: set[str]) -> None:
        self.plugin = None
        self.data = _DryRunDataAPI(scopes)
        self.http = _DryRunHTTPAPI(scopes)
        self.registered_hooks: list[tuple[str, str]] = []

    def register_action(self, hook_name: str, callback, *, priority: int = 50, timeout_ms: int | None = None) -> None:
        _ = callback, priority, timeout_ms
        self._register("action", hook_name)

    def register_async_action(self, hook_name: str, callback, *, priority: int = 50) -> None:
        _ = callback, priority
        self._register("async_action", hook_name)

    def register_filter(self, hook_name: str, callback, *, priority: int = 50, timeout_ms: int | None = None) -> None:
        _ = callback, priority, timeout_ms
        self._register("filter", hook_name)

    def _register(self, hook_kind: str, hook_name: str) -> None:
        hook_name_normalized = str(hook_name or "").strip()
        if not hook_name_normalized:
            raise ValueError("Hook name must be a non-empty string.")
        self.registered_hooks.append((hook_kind, hook_name_normalized))


class PluginZipValidator:
    def __init__(self, archive_path: Path) -> None:
        self.archive_path = Path(archive_path)

    def validate(self) -> ZipValidationReport:
        report = ZipValidationReport(archive_path=self.archive_path)

        if not self.archive_path.exists():
            report.add_error(
                "zip_not_found",
                f"File does not exist: {self.archive_path}",
                hint="Provide a valid path to an existing .zip package.",
            )
            return report

        if not self.archive_path.is_file():
            report.add_error(
                "zip_not_file",
                f"Path is not a file: {self.archive_path}",
                hint="Provide a path to a ZIP file, not a directory.",
            )
            return report

        if self.archive_path.suffix.lower() != ".zip":
            report.add_warning(
                "zip_extension_unexpected",
                f"File extension is '{self.archive_path.suffix or '(none)'}', expected '.zip'.",
                hint="Rename or rebuild the archive as a .zip file.",
            )

        members = self._read_archive_members(report)
        if members is None:
            return report

        self._validate_archive_structure(members, report)
        if report.has_blocking_errors:
            return report

        with tempfile.TemporaryDirectory(prefix="plugin_validate_zip_") as temp_dir:
            temp_root = Path(temp_dir)
            plugin_root = self._extract_plugin_root(temp_root, report)
            if plugin_root is None:
                return report

            report.plugin_root = plugin_root
            manifest = self._load_manifest(plugin_root, report)
            if manifest is None:
                return report

            report.manifest = manifest
            report.add_info(
                "manifest_loaded",
                f"Manifest loaded for '{manifest.slug}' ({manifest.version}).",
            )

            self._validate_manifest_structure(manifest, report)
            self._validate_schema_consistency(manifest, report)

            inferred_scopes, hook_names = self._scan_python_sources(plugin_root)
            self._validate_scope_consistency(manifest, inferred_scopes, report)
            self._report_detected_hooks(hook_names, report)

            module = self._import_entrypoint_module(plugin_root, manifest, report)
            if module is not None:
                self._validate_register_signature(module, report)
                self._dry_run_register(module, manifest, report)

        return report

    def _read_archive_members(self, report: ZipValidationReport) -> list[zipfile.ZipInfo] | None:
        try:
            with zipfile.ZipFile(self.archive_path, "r") as archive:
                members = archive.infolist()
        except zipfile.BadZipFile:
            report.add_error(
                "zip_invalid",
                "Archive is not a valid ZIP file.",
                hint="Rebuild the package with a standard ZIP tool and try again.",
            )
            return None
        except Exception as exc:
            report.add_error(
                "zip_open_failed",
                f"Unable to read archive: {exc}",
                hint="Check file permissions and archive integrity.",
            )
            return None

        if not members:
            report.add_error(
                "zip_empty",
                "Archive is empty.",
                hint="Package at least manifest.json and entrypoint.py.",
            )
            return None

        return members

    def _validate_archive_structure(self, members: list[zipfile.ZipInfo], report: ZipValidationReport) -> None:
        manifest_files: list[str] = []
        unsafe_paths: list[str] = []

        for member in members:
            member_name = str(member.filename or "")
            member_path = Path(member_name)

            if member_path.is_absolute() or ".." in member_path.parts:
                unsafe_paths.append(member_name)

            if member_path.name == "manifest.json" and "__MACOSX" not in member_path.parts:
                manifest_files.append(member_name)

        if unsafe_paths:
            report.add_error(
                "zip_unsafe_paths",
                "Archive contains unsafe paths that could escape extraction directory.",
                hint=f"Remove unsafe entries such as: {', '.join(sorted(unsafe_paths)[:3])}",
            )

        if not manifest_files:
            report.add_error(
                "manifest_missing",
                "ZIP does not include manifest.json.",
                hint="Add exactly one manifest.json at archive root or plugin subfolder.",
            )
            return

        if len(manifest_files) > 1:
            preview = ", ".join(sorted(manifest_files)[:3])
            report.add_error(
                "manifest_multiple",
                "ZIP contains multiple manifest.json files.",
                hint=f"Keep exactly one plugin package per ZIP. Found: {preview}",
            )

    def _extract_plugin_root(self, temp_root: Path, report: ZipValidationReport) -> Path | None:
        try:
            with zipfile.ZipFile(self.archive_path, "r") as archive:
                _safe_extract_zip(archive, temp_root)
        except PluginManifestError as exc:
            report.add_error(
                "zip_extract_blocked",
                str(exc),
                hint="Remove path traversal or absolute paths from the archive.",
            )
            return None
        except zipfile.BadZipFile:
            report.add_error("zip_invalid", "Archive is not a valid ZIP file.")
            return None
        except Exception as exc:
            report.add_error("zip_extract_failed", f"Failed to extract archive: {exc}")
            return None

        try:
            return _resolve_zip_plugin_root(temp_root)
        except PluginManifestError as exc:
            report.add_error("zip_root_invalid", str(exc))
            return None

    def _load_manifest(self, plugin_root: Path, report: ZipValidationReport) -> PluginManifest | None:
        try:
            manifest = load_manifest_from_directory(plugin_root)
        except PluginManifestError as exc:
            report.add_error(
                "manifest_invalid",
                str(exc),
                hint="Fix manifest.json shape and required fields (slug, name, version).",
            )
            return None
        except Exception as exc:
            report.add_error("manifest_load_failed", f"Unexpected manifest loading failure: {exc}")
            return None

        return manifest

    def _validate_manifest_structure(self, manifest: PluginManifest, report: ZipValidationReport) -> None:
        if len(manifest.slug) > 120:
            report.add_error(
                "slug_too_long",
                f"Manifest slug '{manifest.slug}' exceeds 120 characters.",
                hint="Use a shorter kebab-case slug.",
            )
        if not KEBAB_CASE_RE.fullmatch(manifest.slug):
            report.add_warning(
                "slug_not_kebab_case",
                f"Manifest slug '{manifest.slug}' is not strict kebab-case.",
                hint="Use lowercase letters, numbers, and single dashes.",
            )

        scopes = [scope for scope in manifest.scopes if str(scope).strip()]
        scope_set = set(scopes)

        unknown_scopes = sorted(scope_set - KNOWN_SCOPES)
        if unknown_scopes:
            report.add_warning(
                "scope_unknown",
                f"Manifest declares unknown scopes: {', '.join(unknown_scopes)}.",
                hint=f"Use known scopes: {', '.join(sorted(KNOWN_SCOPES))}.",
            )

        if len(scopes) != len(scope_set):
            report.add_warning(
                "scope_duplicates",
                "Manifest contains duplicate scope values.",
                hint="Keep each scope only once.",
            )

        dependency_slugs = [dep.slug for dep in manifest.dependencies]
        if manifest.slug in dependency_slugs:
            report.add_error(
                "dependency_self_reference",
                f"Plugin '{manifest.slug}' cannot depend on itself.",
                hint="Remove self-reference from dependencies.",
            )

        duplicate_dependencies = sorted(
            {
                dep_slug
                for dep_slug in dependency_slugs
                if dep_slug and dependency_slugs.count(dep_slug) > 1
            }
        )
        if duplicate_dependencies:
            report.add_warning(
                "dependency_duplicates",
                f"Duplicate dependencies found: {', '.join(duplicate_dependencies)}.",
                hint="Keep each dependency slug once.",
            )

    def _validate_schema_consistency(self, manifest: PluginManifest, report: ZipValidationReport) -> None:
        schema = manifest.config_schema or {}
        default_config = manifest.default_config or {}
        env_vars = manifest.env_vars or {}

        for config_key, env_var_name in env_vars.items():
            if not ENV_VAR_RE.fullmatch(str(env_var_name or "")):
                report.add_warning(
                    "env_var_name_unusual",
                    f"env_vars['{config_key}'] = '{env_var_name}' does not match conventional ENV_VAR format.",
                    hint="Use uppercase snake case, e.g. MY_PLUGIN_API_KEY.",
                )

        if not schema:
            if default_config:
                report.add_info(
                    "config_schema_missing",
                    "No config_schema provided. Admin form fields will not be generated automatically.",
                    hint="Add config.schema.json or inline config_schema for non-technical admin editing.",
                )
            return

        properties = schema.get("properties") if isinstance(schema, dict) else None
        if properties is None:
            properties = {}

        if not isinstance(properties, dict):
            report.add_error(
                "schema_properties_invalid",
                "config_schema.properties must be an object.",
                hint="Use JSON object: {\"properties\": {\"field\": {...}}}.",
            )
            return

        non_object_fields = [key for key, value in properties.items() if not isinstance(value, dict)]
        if non_object_fields:
            report.add_error(
                "schema_property_type_invalid",
                f"config_schema properties must be objects. Invalid keys: {', '.join(non_object_fields)}.",
            )
            return

        required_raw = schema.get("required") if isinstance(schema, dict) else []
        if required_raw and not isinstance(required_raw, list):
            report.add_error(
                "schema_required_invalid",
                "config_schema.required must be a list of strings.",
                hint="Example: \"required\": [\"api_key\"].",
            )
            return

        required_keys = [str(item).strip() for item in (required_raw or []) if str(item).strip()]
        missing_required_properties = sorted([key for key in required_keys if key not in properties])
        if missing_required_properties:
            report.add_warning(
                "schema_required_missing_property",
                "config_schema.required references keys missing in properties: "
                + ", ".join(missing_required_properties)
                + ".",
                hint="Define these fields in properties or remove them from required.",
            )

        property_keys = set(properties.keys())
        extra_default_keys = sorted(set(default_config.keys()) - property_keys)
        if extra_default_keys:
            report.add_warning(
                "default_config_extra_keys",
                "default_config defines keys that are not present in config_schema.properties: "
                + ", ".join(extra_default_keys)
                + ".",
                hint="Add schema properties for those keys or remove unused defaults.",
            )

        extra_env_keys = sorted(set(env_vars.keys()) - property_keys)
        if extra_env_keys:
            report.add_warning(
                "env_vars_extra_keys",
                "env_vars maps keys that are not present in config_schema.properties: "
                + ", ".join(extra_env_keys)
                + ".",
                hint="Map only fields that exist in config schema.",
            )

        required_without_fallback = sorted(
            [key for key in required_keys if key not in default_config and key not in env_vars]
        )
        if required_without_fallback:
            report.add_info(
                "required_without_default_or_env",
                "Required fields without default/env fallback must be configured manually in admin: "
                + ", ".join(required_without_fallback)
                + ".",
            )

    def _scan_python_sources(self, plugin_root: Path) -> tuple[set[str], set[str]]:
        inferred_scopes: set[str] = set()
        detected_hooks: set[str] = set()

        for py_file in plugin_root.rglob("*.py"):
            if "__pycache__" in py_file.parts:
                continue

            try:
                source = py_file.read_text(encoding="utf-8")
            except Exception:
                source = py_file.read_text(encoding="utf-8", errors="ignore")

            for scope_name, pattern in SCOPE_USAGE_PATTERNS.items():
                if pattern.search(source):
                    inferred_scopes.add(scope_name)

            for hook_name in REGISTERED_HOOK_RE.findall(source):
                normalized_hook = str(hook_name or "").strip()
                if normalized_hook:
                    detected_hooks.add(normalized_hook)

        return inferred_scopes, detected_hooks

    def _validate_scope_consistency(
        self,
        manifest: PluginManifest,
        inferred_scopes: set[str],
        report: ZipValidationReport,
    ) -> None:
        declared_scopes = set(manifest.scopes or [])

        missing_scopes = sorted(scope for scope in inferred_scopes if scope not in declared_scopes)
        for scope_name in missing_scopes:
            report.add_error(
                f"scope_missing_{scope_name.replace(':', '_')}",
                f"Code usage suggests scope '{scope_name}' is required but it is missing in manifest.scopes.",
                hint=f"Add '{scope_name}' to manifest.scopes.",
            )

        extra_scopes = sorted(
            scope
            for scope in declared_scopes
            if scope in KNOWN_SCOPES and scope not in inferred_scopes
        )
        if extra_scopes:
            report.add_info(
                "scope_declared_not_detected",
                "Manifest declares scopes not detected by static scan: " + ", ".join(extra_scopes) + ".",
                hint="This can be valid for dynamic code paths; keep only scopes the plugin truly needs.",
            )

    def _report_detected_hooks(self, hook_names: set[str], report: ZipValidationReport) -> None:
        if not hook_names:
            report.add_warning(
                "hooks_not_detected",
                "Static scan did not detect api.register_* hook registrations.",
                hint="Ensure register(api) calls api.register_filter/action/async_action.",
            )
            return

        ordered_hooks = sorted(hook_names)
        preview = ", ".join(ordered_hooks[:6])
        suffix = "" if len(ordered_hooks) <= 6 else f" ... (+{len(ordered_hooks) - 6} more)"
        report.add_info("hooks_detected", f"Detected hooks: {preview}{suffix}")

    def _import_entrypoint_module(
        self,
        plugin_root: Path,
        manifest: PluginManifest,
        report: ZipValidationReport,
    ) -> ModuleType | None:
        entrypoint_path = (plugin_root / manifest.entrypoint).resolve()
        plugin_root_resolved = plugin_root.resolve()

        try:
            entrypoint_path.relative_to(plugin_root_resolved)
        except ValueError:
            report.add_error(
                "entrypoint_outside_plugin",
                f"Entrypoint '{manifest.entrypoint}' resolves outside plugin directory.",
                hint="Use a relative path inside the plugin package.",
            )
            return None

        if not entrypoint_path.exists() or not entrypoint_path.is_file():
            report.add_error(
                "entrypoint_missing",
                f"Entrypoint file not found: {manifest.entrypoint}",
                hint="Create the file or fix manifest.entrypoint.",
            )
            return None

        module_name = f"plugin_validate_{manifest.slug.replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, entrypoint_path)
        if not spec or not spec.loader:
            report.add_error(
                "entrypoint_spec_failed",
                f"Unable to create import spec for '{manifest.entrypoint}'.",
            )
            return None

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            report.add_error(
                "entrypoint_import_failed",
                f"Entrypoint import failed: {type(exc).__name__}: {exc}",
                hint=self._format_traceback_hint(exc),
            )
            return None

        report.add_info("entrypoint_import_ok", f"Entrypoint imported: {manifest.entrypoint}")
        return module

    def _validate_register_signature(self, module: ModuleType, report: ZipValidationReport) -> None:
        register_func = getattr(module, "register", None)
        if register_func is None:
            report.add_error(
                "register_missing",
                "Entrypoint does not define register(api).",
                hint="Add a top-level function: def register(api): ...",
            )
            return

        if not callable(register_func):
            report.add_error("register_not_callable", "Entrypoint attribute 'register' exists but is not callable.")
            return

        if inspect.iscoroutinefunction(register_func):
            report.add_error(
                "register_async_not_supported",
                "register(api) cannot be async.",
                hint="Use synchronous register(api) and register async callbacks via api.register_async_action().",
            )
            return

        try:
            signature = inspect.signature(register_func)
        except Exception:
            report.add_warning("register_signature_unknown", "Unable to inspect register(api) signature.")
            return

        if not self._can_call_register_with_single_api_arg(signature):
            report.add_error(
                "register_bad_signature",
                f"register signature '{signature}' is not compatible with register(api).",
                hint="Define register with at least one positional parameter for the API object.",
            )
            return

        report.add_info("register_signature_ok", f"register(api) signature looks valid: {signature}")

    def _dry_run_register(self, module: ModuleType, manifest: PluginManifest, report: ZipValidationReport) -> None:
        register_func = getattr(module, "register", None)
        if not callable(register_func):
            return

        dry_api = _DryRunPluginAPI(scopes=set(manifest.scopes or []))
        try:
            register_func(dry_api)
        except Exception as exc:
            report.add_warning(
                "register_dry_run_failed",
                f"register(api) raised during dry-run: {type(exc).__name__}: {exc}",
                hint=(
                    "Validator uses a dry-run API with api.plugin=None. "
                    "If your register() requires a real DB plugin object, ignore this warning."
                ),
            )
            return

        if not dry_api.registered_hooks:
            report.add_warning(
                "register_no_hooks",
                "register(api) completed but did not register any hooks.",
                hint="If intentional (lifecycle-only plugin), this warning can be ignored.",
            )
            return

        preview = ", ".join(f"{kind}:{name}" for kind, name in dry_api.registered_hooks[:6])
        suffix = "" if len(dry_api.registered_hooks) <= 6 else f" ... (+{len(dry_api.registered_hooks) - 6} more)"
        report.add_info(
            "register_dry_run_ok",
            f"register(api) dry-run succeeded and registered hooks: {preview}{suffix}",
        )

    def _can_call_register_with_single_api_arg(self, signature: inspect.Signature) -> bool:
        positional = [
            parameter
            for parameter in signature.parameters.values()
            if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        has_varargs = any(
            parameter.kind == inspect.Parameter.VAR_POSITIONAL
            for parameter in signature.parameters.values()
        )
        if has_varargs:
            return True

        required_positional = sum(1 for parameter in positional if parameter.default is inspect.Signature.empty)
        return required_positional <= 1 and bool(positional)

    def _format_traceback_hint(self, exc: Exception) -> str:
        traceback_frames = traceback.extract_tb(exc.__traceback__)
        if not traceback_frames:
            return "Inspect the traceback above and fix the import/runtime error."

        frame = traceback_frames[-1]
        filename = Path(frame.filename).name
        return f"Check {filename}:{frame.lineno} in function '{frame.name}'."


class Command(BaseCommand):
    help = "Validate plugin ZIP package before upload/install and print actionable diagnostics."

    def add_arguments(self, parser):
        parser.add_argument("archive_path", type=str, help="Path to plugin ZIP package.")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Treat warnings as blocking failures (non-zero exit).",
        )

    def handle(self, archive_path, **options):
        strict = bool(options.get("strict"))

        validator = PluginZipValidator(Path(archive_path))
        report = validator.validate()

        self._print_report(report, strict=strict)

        has_failures = bool(report.errors) or (strict and bool(report.warnings))
        if has_failures:
            if strict and report.warnings and not report.errors:
                raise CommandError("Plugin package validation failed in strict mode (warnings treated as errors).")
            raise CommandError("Plugin package validation failed.")

    def _print_report(self, report: ZipValidationReport, *, strict: bool) -> None:
        self.stdout.write(f"Validating plugin package: {report.archive_path}")

        if report.manifest is not None:
            self.stdout.write(
                f"Resolved plugin: {report.manifest.slug} v{report.manifest.version} "
                f"(entrypoint: {report.manifest.entrypoint})"
            )

        self._print_message_group("ERRORS", report.errors, style=self.style.ERROR)
        self._print_message_group("WARNINGS", report.warnings, style=self.style.WARNING)
        self._print_message_group("INFO", report.infos, style=self.style.SUCCESS)

        validation_passed = not report.errors and not (strict and report.warnings)
        status_text = "PASS" if validation_passed else "FAIL"

        self.stdout.write("")
        self.stdout.write("Summary")
        if validation_passed:
            self.stdout.write(self.style.SUCCESS(f"Validation status: {status_text}"))
            self.stdout.write(self.style.SUCCESS("Package upload readiness: READY"))
        else:
            self.stdout.write(self.style.ERROR(f"Validation status: {status_text}"))
            self.stdout.write(self.style.ERROR("Package upload readiness: BLOCKED"))

        self.stdout.write(f"Blocking errors: {len(report.errors)}")
        self.stdout.write(f"Warnings: {len(report.warnings)}")
        self.stdout.write(f"Info: {len(report.infos)}")

        if strict:
            self.stdout.write("Mode: strict")

    def _print_message_group(self, title: str, messages: list[ValidationMessage], *, style) -> None:
        self.stdout.write("")
        self.stdout.write(style(f"{title} ({len(messages)})"))
        if not messages:
            self.stdout.write("  - none")
            return

        for message in messages:
            for line in message.as_lines():
                self.stdout.write(f"  - {line}")
