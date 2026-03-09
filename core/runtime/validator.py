import json

from .errors import InputValidationError


class ValidationResult:
    def __init__(self, ok: bool, params: dict):
        self.ok = ok
        self.params = params


class ToolValidator:
    """Three-phase tool argument validation."""

    def validate(self, schema: dict, args: dict) -> ValidationResult:
        properties = schema.get("parameters", {}).get("properties", {})
        required = schema.get("parameters", {}).get("required", [])

        # Phase 1: required fields
        missing = [f for f in required if f not in args]
        if missing:
            msgs = [f"The required parameter `{f}` is missing" for f in missing]
            raise InputValidationError("\n".join(msgs))

        # Phase 2: type check
        for name, val in args.items():
            prop = properties.get(name, {})
            expected = prop.get("type")
            if expected and not self._type_matches(val, expected):
                actual = type(val).__name__
                raise InputValidationError(
                    f"The parameter `{name}` type is expected as `{expected}` but provided as `{actual}`"
                )

        # Phase 3: enum validation
        issues = self._validate_enum(properties, args)
        if issues:
            raise InputValidationError(json.dumps(issues))

        return ValidationResult(ok=True, params=args)

    def _type_matches(self, val, expected: str) -> bool:
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        expected_type = type_map.get(expected)
        if expected_type is None:
            return True
        return isinstance(val, expected_type)

    def _validate_enum(self, properties: dict, args: dict) -> list:
        issues = []
        for name, val in args.items():
            prop = properties.get(name, {})
            enum_vals = prop.get("enum")
            if enum_vals and val not in enum_vals:
                issues.append({"field": name, "expected": enum_vals, "got": val})
        return issues
