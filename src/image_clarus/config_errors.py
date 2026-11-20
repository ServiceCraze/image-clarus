"""Shared configuration error type."""


class ConfigurationError(ValueError):
    """A sanitized preflight failure with a stable category."""

    def __init__(self, message, category="configuration"):
        if category == "configuration" and not message.startswith(
            ("Invalid configuration", "Cannot load configuration")
        ):
            message = f"Invalid configuration: {message}"
        super().__init__(message)
        self.category = category
