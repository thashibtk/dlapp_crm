from django.db import transaction
from django.utils import timezone
from .models import EmployeeIdSequence

def next_employee_id():
    year = timezone.now().year
    with transaction.atomic():
        seq, _ = EmployeeIdSequence.objects.select_for_update().get_or_create(year=year)
        seq.last_number += 1
        seq.save(update_fields=["last_number"])
        return f"EMP{year}-{seq.last_number:04d}"

