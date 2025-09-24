import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from core import models as M

User = get_user_model()

DEFAULT_PASSWORD = os.getenv("DLAPP_SEED_PASSWORD", "ChangeMe123!")

ROLE_DEFS = {
    # username        user_type              is_superuser  is_staff  group_name
    "superadmin":   ("super_user",               True,      True,   "SuperUser"),
    "dr_ali":       ("doctor",                  False,      True,   "Doctor"),
    "dr_junior":    ("consulting_doctor",       False,      True,   "ConsultingDoctor"),
    "ops_mgr":      ("operation_manager",       False,      True,   "OperationsManager"),
    "reception1":   ("staff",                   False,      True,   "Receptionist"),
    "clinic_mgr":   ("pharmacy_manager",        False,      True,   "PharmacyManager"),
    "cro1":         ("cro",                     False,      True,   "CRO"),
}

def perms_for(model, actions=("add", "change", "delete", "view")):
    ct = ContentType.objects.get_for_model(model)
    out = []
    for act in actions:
        try:
            out.append(Permission.objects.get(content_type=ct, codename=f"{act}_{model._meta.model_name}"))
        except Permission.DoesNotExist:
            # In case some models don’t have all perms
            pass
    return out

def grant(group, model_list, actions=("add", "change", "delete", "view")):
    for model in model_list:
        for p in perms_for(model, actions):
            group.permissions.add(p)

def ensure_groups_and_permissions():
    """
    Creates all role groups & attaches permissions exactly as discussed.
    Safe to run multiple times.
    """
    groups = {
        "SuperUser": Group.objects.get_or_create(name="SuperUser")[0],
        "Doctor": Group.objects.get_or_create(name="Doctor")[0],
        "ConsultingDoctor": Group.objects.get_or_create(name="ConsultingDoctor")[0],
        "OperationsManager": Group.objects.get_or_create(name="OperationsManager")[0],
        "PharmacyManager": Group.objects.get_or_create(name="PharmacyManager")[0],   # pharmacy manager
        "Receptionist": Group.objects.get_or_create(name="Receptionist")[0],
        "CRO": Group.objects.get_or_create(name="CRO")[0],
        "Staff": Group.objects.get_or_create(name="Staff")[0],
    }

    all_models = [
        M.User, M.UserProfile,
        M.Patient, M.PatientMedicalHistory, M.HairConsultation, M.ConsultationPhoto,
        M.TreatmentPlan, M.Appointment, M.TreatmentSession,
        M.FollowUp, M.ProgressPhoto,
        M.MedicineCategory, M.Medicine, M.MedicineStock, M.StockTransaction,
        M.Bill, M.BillItem, M.Payment,
        M.LeadSource, M.Lead,
        M.ExpenseCategory, M.Expense,
        M.DailyReport, M.AppointmentSlot,
    ]

    # Doctor = full access
    grant(groups["Doctor"], all_models)

    # Consulting Doctor = limited clinical access
    consulting_models = [
        M.Patient, M.PatientMedicalHistory, M.HairConsultation, M.ConsultationPhoto,
        M.TreatmentPlan, M.Appointment, M.TreatmentSession,
        M.FollowUp, M.ProgressPhoto,
    ]
    grant(groups["ConsultingDoctor"], consulting_models, actions=("add", "change", "view"))
    grant(groups["ConsultingDoctor"], [
        M.Bill, M.BillItem, M.Payment,
        M.MedicineCategory, M.Medicine, M.MedicineStock, M.AppointmentSlot,
    ], actions=("view",))

    # Operations Manager = full access
    grant(groups["OperationsManager"], all_models)

    # Clinic Manager = manage medicine stocks + read patients/billing/appointments
    grant(groups["PharmacyManager"], [M.MedicineCategory, M.Medicine, M.MedicineStock, M.StockTransaction])
    grant(groups["PharmacyManager"], [M.Patient, M.Appointment, M.Bill, M.BillItem, M.Payment], actions=("view",))

    # Receptionist = patient registration + billing + see appointments
    grant(groups["Receptionist"], [M.Patient, M.Bill, M.BillItem, M.Payment], actions=("add", "change", "view"))
    grant(groups["Receptionist"], [M.Appointment], actions=("add", "change", "view"))

    # CRO = manage leads + create appointments (visible to receptionist) + view patients
    grant(groups["CRO"], [M.LeadSource, M.Lead], actions=("add", "change", "view"))
    grant(groups["CRO"], [M.Appointment], actions=("add", "change", "view"))
    grant(groups["CRO"], [M.Patient], actions=("view",))

    # Staff = mostly view
    grant(groups["Staff"], [M.Patient, M.Appointment], actions=("view",))
    grant(groups["Staff"], [M.DailyReport], actions=("view",))

    return groups

def ensure_user(username, user_type, is_superuser, is_staff, group_name):
    u, created = User.objects.get_or_create(username=username, defaults={
        "user_type": user_type,
        "is_superuser": is_superuser,
        "is_staff": is_staff,
    })
    if created:
        # set password on first creation
        u.set_password(DEFAULT_PASSWORD)
        u.save()
    else:
        # keep account, ensure flags & user_type are correct
        updates = []
        if u.user_type != user_type:
            u.user_type = user_type
            updates.append("user_type")
        if u.is_superuser != is_superuser:
            u.is_superuser = is_superuser
            updates.append("is_superuser")
        if u.is_staff != is_staff:
            u.is_staff = is_staff
            updates.append("is_staff")
        if updates:
            u.save()

    # ensure group membership
    group = Group.objects.get(name=group_name)
    u.groups.add(group)
    return u, created

class Command(BaseCommand):
    help = "Seed (idempotent) role users and groups for Dlapp CRM"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Reset ALL seeded users' passwords to DLAPP_SEED_PASSWORD (default: ChangeMe123!)",
        )

    def handle(self, *args, **opts):
        self.stdout.write(self.style.MIGRATE_HEADING("Ensuring groups & permissions..."))
        groups = ensure_groups_and_permissions()

        self.stdout.write(self.style.MIGRATE_HEADING("Seeding users..."))
        for username, (user_type, is_superuser, is_staff, group_name) in ROLE_DEFS.items():
            u, created = ensure_user(username, user_type, is_superuser, is_staff, group_name)
            flag = "created" if created else "exists"
            self.stdout.write(f" - {username} [{group_name}] -> {flag}")

        if opts["reset_passwords"]:
            for username in ROLE_DEFS.keys():
                try:
                    u = User.objects.get(username=username)
                    u.set_password(DEFAULT_PASSWORD)
                    u.save()
                    self.stdout.write(self.style.SUCCESS(f"   reset password: {username}"))
                except User.DoesNotExist:
                    pass

        self.stdout.write(self.style.SUCCESS("Done."))
        self.stdout.write(self.style.HTTP_INFO(
            f"Default password: {DEFAULT_PASSWORD} (override with env DLAPP_SEED_PASSWORD)"
        ))
