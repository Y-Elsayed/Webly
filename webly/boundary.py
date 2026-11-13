"""Sanitized error normalization at the supported host API boundary."""

from functools import wraps

from filelock import Timeout

from webly.contracts import (
    ArtifactError,
    ConfigurationError,
    CoreError,
    PublicationConflict,
    current_operation,
)


def core_boundary(*, configuration=False):
    def decorate(function):
        @wraps(function)
        def call(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except CoreError:
                raise
            except (OSError, ValueError, RuntimeError, Timeout) as exc:
                context = kwargs.get("context") or current_operation()
                if isinstance(exc, Timeout):
                    if context:
                        context.check()
                    error = PublicationConflict
                    message = "Resource operation is busy; reconcile before retrying"
                elif configuration and isinstance(exc, ValueError):
                    error, message = ConfigurationError, "Invalid runtime configuration"
                else:
                    error, message = ArtifactError, f"{function.__name__} failed ({type(exc).__name__})"
                raise error(
                    message,
                    operation_id=context.operation_id if context else None,
                    outcome=context.outcome if context else None,
                ) from None

        return call

    return decorate
