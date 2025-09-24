# signals.py
from django.db import transaction
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import Group

from .models import (
    User, UserProfile,
    Medicine, MedicineStock, StockTransaction,
    BillItem
)
from .utils import next_employee_id


# -----------------------------
# Users / Profiles / Groups
# -----------------------------

ROLE_GROUP_MAP = {
    'doctor': 'Doctor',
    'consulting_doctor': 'ConsultingDoctor',
    'operation_manager': 'OperationsManager',
    'pharmacy_manager': 'PharmacyManager',
    'receptionist': 'Receptionist',
    'staff': 'Staff',
    'cro': 'CRO',
    'super_user': 'SuperUser',
}

@receiver(post_save, sender=User)
def create_profile_and_assign_group(sender, instance, created, **kwargs):
    if not created:
        return

    profile, _ = UserProfile.objects.get_or_create(user=instance)

    if instance.user_type in {"operation_manager", "pharmacy_manager", "staff", "cro", "consulting_doctor"}:
        if not profile.employee_id:
            profile.employee_id = next_employee_id()
            profile.save(update_fields=["employee_id"])

    group_name = ROLE_GROUP_MAP.get(instance.user_type)
    if group_name:
        group, _ = Group.objects.get_or_create(name=group_name)
        instance.groups.add(group)


# -----------------------------
# Billing
# -----------------------------

@receiver(pre_save, sender=BillItem)
def infer_billitem_defaults(sender, instance, **kwargs):
    """
    Infer kind and default fields from selected service/medicine.
    Does not save; just sets values on the instance before save().
    """
    # Infer kind if user picked one side
    if not instance.kind:
        if instance.service_id and not instance.medicine_id:
            instance.kind = 'service'
        elif instance.medicine_id and not instance.service_id:
            instance.kind = 'pharmacy'

    # Defaults by kind
    if instance.kind == 'service' and instance.service_id:
        if not instance.description:
            instance.description = instance.service.name
        if not instance.unit_price or instance.unit_price == 0:
            instance.unit_price = instance.service.default_price or 0

    elif instance.kind == 'pharmacy' and instance.medicine_id:
        if not instance.description:
            s = instance.medicine.strength
            instance.description = f"{instance.medicine.name}{f' ({s})' if s else ''}"
        if not instance.unit_price or instance.unit_price == 0:
            instance.unit_price = instance.medicine.selling_price or 0

@receiver(post_delete, sender=BillItem)
def billitem_deleted(sender, instance, **kwargs):
    """Recompute bill totals when an item is removed."""
    if instance.bill_id:
        instance.bill.recalculate(save=True)

# NOTE: We intentionally do NOT recalc on Bill.post_save to avoid recursion.
# If tax/discount change, call bill.recalculate(save=True) in your view after saving the header.


# -----------------------------
# Inventory / Stock
# -----------------------------

@receiver(post_save, sender=Medicine)
def create_stock_row(sender, instance, created, **kwargs):
    """Ensure a stock row exists for each new medicine."""
    if created:
        MedicineStock.objects.get_or_create(
            medicine=instance,
            defaults={'current_quantity': 0, 'reserved_quantity': 0}
        )

def _apply_stock_delta(medicine, delta, user=None):
    """
    Safely apply a stock delta with row lock.
    Quantity sign (±) must already be correct in the StockTransaction.
    """
    with transaction.atomic():
        stock, _ = MedicineStock.objects.select_for_update().get_or_create(
            medicine=medicine,
            defaults={'current_quantity': 0, 'reserved_quantity': 0}
        )
        new_qty = stock.current_quantity + delta
        if new_qty < 0:
            raise ValueError(
                f"Insufficient stock for {medicine.name}: would go negative ({new_qty})."
            )
        stock.current_quantity = new_qty
        stock.save(update_fields=['current_quantity'])

@receiver(pre_save, sender=StockTransaction)
def remember_old_fields(sender, instance, **kwargs):
    """
    Cache old quantity and medicine so we can compute a correct delta on update,
    including the case where the medicine itself changes.
    """
    if instance.pk:
        try:
            old = StockTransaction.objects.get(pk=instance.pk)
            instance._old_quantity = old.quantity or 0
            instance._old_medicine_id = old.medicine_id
        except StockTransaction.DoesNotExist:
            instance._old_quantity = 0
            instance._old_medicine_id = None
    else:
        instance._old_quantity = 0
        instance._old_medicine_id = None

@receiver(post_save, sender=StockTransaction)
def apply_stock_on_save(sender, instance, created, **kwargs):
    """
    Keep stock in sync:
      - On create: apply full quantity.
      - On update: if medicine changed, revert old qty on old med then apply full new qty on new med;
                   else apply (new - old) on the same med.
    """
    old_qty = getattr(instance, "_old_quantity", 0) or 0
    old_med = getattr(instance, "_old_medicine_id", None)
    new_qty = instance.quantity or 0
    new_med = instance.medicine_id

    if old_med and old_med != new_med:
        # Revert entire old qty on the old medicine
        _apply_stock_delta(Medicine.objects.get(pk=old_med), -old_qty, user=instance.created_by)
        # Apply full new qty on the new medicine
        _apply_stock_delta(instance.medicine, new_qty, user=instance.created_by)
    else:
        delta = new_qty - old_qty
        if delta:
            _apply_stock_delta(instance.medicine, delta, user=instance.created_by)

@receiver(post_delete, sender=StockTransaction)
def revert_stock_on_delete(sender, instance, **kwargs):
    """Deleting a transaction should revert its effect."""
    if instance.quantity:
        _apply_stock_delta(instance.medicine, -instance.quantity, user=instance.created_by)


