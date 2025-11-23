from django import template

register = template.Library()

_STATUS_LABELS = {
    "draft": "Draft",
    "open": "Open",
    "published": "Open",
    "closed": "Closed",
    "archived": "Archived",
}


@register.filter
def status_label(value):
    if not isinstance(value, str):
        return value
    normalized = value.lower()
    return _STATUS_LABELS.get(normalized, value.capitalize())
