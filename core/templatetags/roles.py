from django import template
register = template.Library()

@register.filter
def in_group(user, group_name: str) -> bool:
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name=group_name).exists()


