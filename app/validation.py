"""Validate a public submission against the widget's own field definitions. Never trust the client."""
import re

EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")
TEL = re.compile(r"^\+?[0-9 ()-]{6,20}$")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class SubmissionInvalid(Exception):
    def __init__(self, errors: list[dict]):
        super().__init__("invalid submission")
        self.errors = errors


def validate(widget, data: dict) -> dict:
    """Returns the cleaned field values. Unknown fields, wrong types and over-long values are errors (422)."""
    if not isinstance(data, dict):
        raise SubmissionInvalid([{"field": "fields", "error": "must be an object of field values"}])
    specs = {f["name"]: f for f in widget.fields}
    errors, clean = [], {}
    for k in data:
        if k not in specs:
            errors.append({"field": k, "error": "unknown field"})
    for name, f in specs.items():
        v = data.get(name)
        if v is None or (isinstance(v, str) and not v.strip()):
            if f.get("required"):
                errors.append({"field": name, "error": "required"})
            continue
        if not isinstance(v, str):
            errors.append({"field": name, "error": "must be a string"})
            continue
        v = CONTROL.sub("", v).strip()
        if len(v) > f.get("max_length", 200):
            errors.append({"field": name, "error": f"longer than {f.get('max_length', 200)} characters"})
        elif f["type"] == "email" and not EMAIL.match(v):
            errors.append({"field": name, "error": "not a valid email address"})
        elif f["type"] == "tel" and not TEL.match(v):
            errors.append({"field": name, "error": "not a valid phone number"})
        else:
            clean[name] = v
    if errors:
        raise SubmissionInvalid(errors)
    return clean
