from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from core import models

def perms_for(model, actions=('add', 'change', 'delete', 'view')):
    ct = ContentType.objects.get_for_model(model)
    return [Permission.objects.get(content_type=ct, codename=f'{act}_{model._meta.model_name}')
            for act in actions]

class Command(BaseCommand):
    help = "Initialize role groups and permissions"

    def handle(self, *args, **kwargs):
        # Create groups
        groups = {
            'SuperUser': Group.objects.get_or_create(name='SuperUser')[0],
            'Doctor': Group.objects.get_or_create(name='Doctor')[0],
            'ConsultingDoctor': Group.objects.get_or_create(name='ConsultingDoctor')[0],
            'OperationsManager': Group.objects.get_or_create(name='OperationsManager')[0],
            'PharmacyManager': Group.objects.get_or_create(name='PharmacyManager')[0], 
            'Receptionist': Group.objects.get_or_create(name='Receptionist')[0],
            'CRO': Group.objects.get_or_create(name='CRO')[0],
            'Staff': Group.objects.get_or_create(name='Staff')[0],
        }

        # All models
        M = models
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

        # helper sets
        def grant(group, model_list, actions=('add','change','delete','view')):
            for model in model_list:
                for p in perms_for(model, actions):
                    group.permissions.add(p)

        # 1) Doctor = full access
        grant(groups['Doctor'], all_models)

        # 2) Consulting Doctor = limited clinical access
        consulting_models = [
            M.Patient, M.PatientMedicalHistory, M.HairConsultation, M.ConsultationPhoto,
            M.TreatmentPlan, M.Appointment, M.TreatmentSession,
            M.FollowUp, M.ProgressPhoto,
        ]
        grant(groups['ConsultingDoctor'], consulting_models, actions=('add','change','view'))
        grant(groups['ConsultingDoctor'], [
            M.Bill, M.BillItem, M.Payment,
            M.MedicineCategory, M.Medicine, M.MedicineStock, M.AppointmentSlot,
        ], actions=('view',))

        # 3) Operations Manager = can create staff + full access
        grant(groups['OperationsManager'], all_models)

        # 4) Clinic Manager (pharmacy manager) = manage medicine stocks (plus view patients/appointments)
        grant(groups['PharmacyManager'], [
            M.MedicineCategory, M.Medicine, M.MedicineStock, M.StockTransaction
        ])
        # read-only elsewhere:
        grant(groups['PharmacyManager'], [
            M.Patient, M.Appointment, M.Bill, M.BillItem, M.Payment
        ], actions=('view',))

        # 5) Receptionist = patient registration + billing + see appointments
        grant(groups['Receptionist'], [
            M.Patient, M.Bill, M.BillItem, M.Payment
        ], actions=('add','change','view'))
        grant(groups['Receptionist'], [M.Appointment], actions=('view','add','change'))

        # 6) CRO = lead management + create appointments (visible to receptionist)
        grant(groups['CRO'], [
            M.LeadSource, M.Lead
        ], actions=('add','change','view'))
        grant(groups['CRO'], [M.Appointment], actions=('add','change','view'))
        # CRO read patients (so they can convert & schedule)
        grant(groups['CRO'], [M.Patient], actions=('view',))

        # 7) Staff = mostly view, limited change where needed (tune later)
        grant(groups['Staff'], [M.Patient, M.Appointment], actions=('view',))
        grant(groups['Staff'], [M.DailyReport], actions=('view',))

        self.stdout.write(self.style.SUCCESS("Role groups & permissions initialized."))
