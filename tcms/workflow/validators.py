from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_steps(value, allow_shared=True):
    if not isinstance(value, list) or len(value) > 200:
        raise ValidationError(_("Provide a list of at most 200 steps."))
    for step in value:
        if not isinstance(step, dict):
            raise ValidationError(_("Each step must be an object."))
        if "shared_id" in step:
            if (
                not allow_shared
                or set(step) != {"shared_id"}
                or type(step["shared_id"]) is not int
                or step["shared_id"] < 1
            ):
                raise ValidationError(_("Invalid shared step reference."))
            continue
        if set(step) - {"action", "expected", "reference"}:
            raise ValidationError(_("Unknown step field."))
        if not isinstance(step.get("action"), str) or not step["action"].strip():
            raise ValidationError(_("Each step needs an action."))
        for key, limit in (("action", 10000), ("expected", 10000), ("reference", 255)):
            content = step.get(key, "")
            if not isinstance(content, str) or len(content) > limit:
                labels = {
                    "action": _("Action"),
                    "expected": _("Expected result"),
                    "reference": _("Reference"),
                }
                raise ValidationError(
                    _("Invalid %(field)s; maximum length is %(limit)d.")
                    % {"field": labels[key], "limit": limit}
                )


def validate_shared_steps(value):
    validate_steps(value, allow_shared=False)


def validate_choices(value):
    if (
        not isinstance(value, list)
        or len(value) > 100
        or any(
            not isinstance(item, str) or not item.strip() or len(item) > 255
            for item in value
        )
        or len(set(value)) != len(value)
    ):
        raise ValidationError(
            _("Choices must be distinct nonempty strings (at most 100).")
        )
