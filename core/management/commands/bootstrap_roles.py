from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from core import models as M

ROLE_GROUPS = [
    "SuperUser", "Doctor", "ConsultingDoctor",
    "OperationsManager", "PharmacyManager",
    "Receptionist", "CRO", "Staff"
]

def perms_for(model, actions=('add','change','delete','view')):
    ct = ContentType.objects.get_for_model(model)
    perms = []
    for act in actions:
        perm = Permission.objects.filter(content_type=ct, codename=f'{act}_{model._meta.model_name}').first()
        if perm:
            perms.append(perm)
    return perms

def grant(group, models, actions=('add','change','delete','view')):
    for model in models:
        for p in perms_for(model, actions):
            group.permissions.add(p)

def ensure_groups_and_permissions():
    groups = {name: Group.objects.get_or_create(name=name)[0] for name in ROLE_GROUPS}

    all_models = [
        M.User, M.UserProfile,
        M.Patient, M.PatientMedicalHistory, M.HairConsultation, M.ConsultationPhoto,
        M.TreatmentPlan, M.Appointment, M.TreatmentSession,
        M.FollowUp, M.ProgressPhoto,
        M.MedicineCategory, M.Medicine, M.MedicineStock, M.StockTransaction,
        M.Bill, M.BillItem, M.Payment,
        M.LeadSource, M.Lead,
        M.ExpenseCategory, M.Expense,
        M.DailyReport
    ]

    # Doctor full access
    grant(groups["Doctor"], all_models)

    # ConsultingDoctor limited
    grant(groups["ConsultingDoctor"], [
        M.Patient, M.PatientMedicalHistory, M.HairConsultation,
        M.ConsultationPhoto, M.TreatmentPlan, M.Appointment,
        M.TreatmentSession, M.FollowUp, M.ProgressPhoto
    ], actions=('add','change','view'))
    grant(groups["ConsultingDoctor"], [M.Bill, M.BillItem, M.Payment], actions=('view',))

    # Ops Manager full
    grant(groups["OperationsManager"], all_models)

    # PharmacyManager
    grant(groups["PharmacyManager"], [M.MedicineCategory, M.Medicine, M.MedicineStock, M.StockTransaction])
    grant(groups["PharmacyManager"], [M.Patient, M.Appointment, M.Bill, M.BillItem, M.Payment], actions=('view',))

    # Receptionist
    grant(groups["Receptionist"], [M.Patient, M.Bill, M.BillItem, M.Payment], actions=('add','change','view'))
    grant(groups["Receptionist"], [M.Appointment], actions=('add','change','view'))

    # CRO
    grant(groups["CRO"], [M.LeadSource, M.Lead], actions=('add','change','view'))
    grant(groups["CRO"], [M.Appointment], actions=('add','change','view'))
    grant(groups["CRO"], [M.Patient], actions=('view',))

    # Staff (view only)
    grant(groups["Staff"], [M.Patient, M.Appointment, M.DailyReport], actions=('view',))

class Command(BaseCommand):
    help = "Bootstrap role groups & permissions (fresh start safe)."

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.MIGRATE_HEADING("Bootstrapping groups & permissions..."))
        ensure_groups_and_permissions()
        self.stdout.write(self.style.SUCCESS("Done. Roles initialized."))
