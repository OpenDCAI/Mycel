import json
import re

from .errors import InputValidationError


def _required_sets(parameters: dict, key: str) -> list[list[str]]:
    value = parameters.get(key, [])
    if not isinstance(value, list):
        return []
    sets: list[list[str]] = []
    for item in value:
        if isinstance(item, dict):
            required = item.get("required", [])
        else:
            required = item
        if isinstance(required, list):
            sets.append([field for field in required if isinstance(field, str)])
    return sets


def _arg_counts_as_present(args: dict, field: str) -> bool:
    if field not in args:
        return False
    value = args[field]
    if value is None:
        return False
    if isinstance(value, str) and value == "":
        return False
    return True


def _required_sets_match(parameters: dict, args: dict) -> bool:
    required = parameters.get("required", [])
    if any(not _arg_counts_as_present(args, field) for field in required):
        return False

    # @@@required-set-contract - some tools need one of several identifier sets
    # before they're valid. Keep that contract in runtime metadata so
    # validator/readiness stay aligned without sending unsupported top-level
    # anyOf/oneOf schema to live providers.
    any_of = _required_sets(parameters, "x-leon-required-any-of") or _required_sets(parameters, "anyOf")
    if any_of:
        return any(all(_arg_counts_as_present(args, field) for field in required) for required in any_of)

    one_of = _required_sets(parameters, "x-leon-required-one-of") or _required_sets(parameters, "oneOf")
    if one_of:
        matches = [required for required in one_of if all(_arg_counts_as_present(args, field) for field in required)]
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
                details = [
                    {
                        "field": field,
                        "error_code": "REQUIRED_FIELD_MISSING",
                        "message": f"The required parameter `{field}` is missing",
                    }
                    for field in missing
                ]
                raise InputValidationError(
                    "\n".join(detail["message"] for detail in details),
                    error_code="REQUIRED_FIELD_MISSING" if len(details) == 1 else "INPUT_CONSTRAINT_VIOLATION",
                    details=details,
                )
            any_of = _required_sets(parameters, "x-leon-required-any-of") or _required_sets(parameters, "anyOf")
            one_of = _required_sets(parameters, "x-leon-required-one-of") or _required_sets(parameters, "oneOf")
            if any_of:
                message = f"Arguments must satisfy one of these required sets: {any_of}"
                raise InputValidationError(
                    message,
                    error_code="REQUIRED_SET_UNSATISFIED",
                    details=[{"error_code": "REQUIRED_SET_UNSATISFIED", "message": message}],
                )
            if one_of:
                message = f"Arguments must satisfy exactly one of these required sets: {one_of}"
                raise InputValidationError(
                    message,
                    error_code="REQUIRED_SET_UNSATISFIED",
                    details=[{"error_code": "REQUIRED_SET_UNSATISFIED", "message": message}],
                )

        # Phase 2: type check
        for name, val in args.items():
            prop = properties.get(name, {})
            expected = prop.get("type")
            if expected and not self._type_matches(val, expected):
                actual = type(val).__name__
                message = f"The parameter `{name}` type is expected as `{expected}` but provided as `{actual}`"
                raise InputValidationError(
                    message,
                    error_code="INVALID_TYPE",
                    details=[
                        {
                            "field": name,
                            "error_code": "INVALID_TYPE",
                            "expected": expected,
                            "actual": actual,
                            "message": message,
                        }
                    ],
                )

        # Phase 3: scalar constraints
        issues = self._validate_scalar_constraints(properties, args)
        if issues:
            raise InputValidationError(
                "\n".join(str(issue["message"]) for issue in issues),
                error_code=str(issues[0]["error_code"]) if len(issues) == 1 else "INPUT_CONSTRAINT_VIOLATION",
                details=issues,
            )

        # Phase 4: enum validation
        issues = self._validate_enum(properties, args)
        if issues:
            raise InputValidationError(
                json.dumps(issues),
                error_code="INVALID_ENUM" if len(issues) == 1 else "INPUT_CONSTRAINT_VIOLATION",
                details=issues,
            )

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

    def _validate_enum(self, properties: dict, args: dict) -> list[dict[str, object]]:
        issues: list[dict[str, object]] = []
        for name, val in args.items():
            prop = properties.get(name, {})
            enum_vals = prop.get("enum")
            if enum_vals and val not in enum_vals:
                issues.append(
                    {
                        "field": name,
                        "error_code": "INVALID_ENUM",
                        "expected": enum_vals,
                        "got": val,
                        "message": f"The parameter `{name}` must be one of {enum_vals}, got {val!r}",
                    }
                )
        return issues

    def _validate_scalar_constraints(self, properties: dict, args: dict) -> list[dict[str, object]]:
        issues: list[dict[str, object]] = []
        for name, val in args.items():
            prop = properties.get(name, {})
            if isinstance(val, str):
                min_length = prop.get("minLength")
                if isinstance(min_length, int) and len(val) < min_length:
                    issues.append(
                        {
                            "field": name,
                            "error_code": "STRING_TOO_SHORT",
                            "message": f"The parameter `{name}` must be at least {min_length} characters long",
                            "minimum": min_length,
                        }
                    )
                max_length = prop.get("maxLength")
                if isinstance(max_length, int) and len(val) > max_length:
                    issues.append(
                        {
                            "field": name,
                            "error_code": "STRING_TOO_LONG",
                            "message": f"The parameter `{name}` must be at most {max_length} characters long",
                            "maximum": max_length,
                        }
                    )
                pattern = prop.get("pattern")
                if isinstance(pattern, str) and re.search(pattern, val) is None:
                    issues.append(
                        {
                            "field": name,
                            "error_code": "PATTERN_MISMATCH",
                            "message": f"The parameter `{name}` must match pattern `{pattern}`",
                            "pattern": pattern,
                        }
                    )
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                minimum = prop.get("minimum")
                if isinstance(minimum, (int, float)) and val < minimum:
                    issues.append(
                        {
                            "field": name,
                            "error_code": "NUMBER_TOO_SMALL",
                            "message": f"The parameter `{name}` must be at least {minimum}",
                            "minimum": minimum,
                        }
                    )
                maximum = prop.get("maximum")
                if isinstance(maximum, (int, float)) and val > maximum:
                    issues.append(
                        {
                            "field": name,
                            "error_code": "NUMBER_TOO_LARGE",
                            "message": f"The parameter `{name}` must be at most {maximum}",
                            "maximum": maximum,
                        }
                    )
        return issues
