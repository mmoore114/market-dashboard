"""Validate frozen model graphs without expanding shared nodes into dictionaries."""

from pydantic import BaseModel


class ModelValidationCache:
    """Invocation-local cache, retaining identities to prevent object-ID reuse.

    Every model's declared fields and validators are checked. Only already
    validated immutable identities are shared; model_copy creates a new identity
    and therefore cannot bypass validation. Never persist or globally reuse this
    cache, or use it with mutable contracts.
    """

    def __init__(self):
        self.objects = {}
        self.visiting = set()

    def validate(self, value, expected=None):
        if isinstance(value, BaseModel):
            cls = expected or type(value)
            known = self.objects.get((id(value), cls))
            if known is not None and known[0] is value:
                return known[1]
            if id(value) in self.visiting:
                raise ValueError("Cyclic model input")
            if not cls.model_config.get("frozen"):
                raise ValueError("Frozen model input required")
            self.visiting.add(id(value))
            try:
                fields = {
                    name: self.validate(getattr(value, name))
                    for name in type(value).model_fields
                    if hasattr(value, name)
                }
                result = cls.model_validate(fields)
            finally:
                self.visiting.remove(id(value))
            self.objects[id(value), cls] = (value, result)
            self.objects[id(result), cls] = (result, result)
            return result
        if isinstance(value, tuple):
            return tuple(self.validate(item) for item in value)
        if isinstance(value, list):
            return [self.validate(item) for item in value]
        if isinstance(value, dict):
            return {key: self.validate(item) for key, item in value.items()}
        return value
