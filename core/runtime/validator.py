import json

from .errors import InputValidationError


def _required_sets_match(parameters: dict, args: dict) -> bool:
    required = parameters.get("required", [])
    if any(field not in args for field in required):
        return False

    # @@@anyof-required-contract - some tools need one of several identifier
    # sets before they're valid; treat that as part of the core arg contract so
    # validator and streaming readiness stay aligned.
    any_of = parameters.get("anyOf", [])
    if any_of:
        return any(
            isinstance(option, dict)
            and all(field in args for field in option.get("required", []))
            for option in any_of
        )

    one_of = parameters.get("oneOf", [])
    if one_of:
        matches = [
            option
            for option in one_of
            if isinstance(option, dict) and all(field in args for field in option.get("required", []))
        ]
        return len(matches) == 1

    return True


class ValidationResult:
    def __init__(self, ok: bool, params: dict):
        self.ok = ok
        self.params = params


class ToolValidator:
    """Three-phase tool argument validation."""

    def validate(self, schema: dict, args: dict) -> ValidationResult:
        parameters = schema.get("parameters", {})
        properties = parameters.get("properties", {})

        # Phase 1: required fields
        if not _required_sets_match(parameters, args):
            required = parameters.get("required", [])
            missing = [f for f in required if f not in args]
            if missing:
                msgs = [f"The required parameter `{f}` is missing" for f in missing]
                raise InputValidationError("\n".join(msgs))
            any_of = parameters.get("anyOf", [])
            one_of = parameters.get("oneOf", [])
            if any_of:
                required_sets = [option.get("required", []) for option in any_of if isinstance(option, dict)]
                raise InputValidationError(f"Arguments must satisfy one of these required sets: {required_sets}")
            if one_of:
                required_sets = [option.get("required", []) for option in one_of if isinstance(option, dict)]
                raise InputValidationError(f"Arguments must satisfy exactly one of these required sets: {required_sets}")

        # Phase 2: type check
        for name, val in args.items():
            prop = properties.get(name, {})
            expected = prop.get("type")
            if expected and not self._type_matches(val, expected):
                actual = type(val).__name__
                raise InputValidationError(f"The parameter `{name}` type is expected as `{expected}` but provided as `{actual}`")

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
