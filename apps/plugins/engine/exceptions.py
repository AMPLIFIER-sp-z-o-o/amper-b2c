class PluginEngineError(Exception):
    """Base plugin engine error."""


class PluginDependencyError(PluginEngineError):
    """Raised when plugin dependencies are not satisfied."""


class PluginManifestError(PluginEngineError):
    """Raised when plugin manifest is invalid."""


class PluginScopeError(PluginEngineError):
    """Raised when plugin attempts operation without required scope."""


class PluginAbortAction(PluginEngineError):
    """Plugin requested to stop the current flow."""
