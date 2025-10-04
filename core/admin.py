from django.contrib import admin
from django.core.exceptions import ValidationError
from . import models

# Helper: group check
def in_group(user, name):
    return user.is_superuser or user.groups.filter(name=name).exists()


# ==========================
# USER MANAGEMENT
# ==========================
@admin.register(models.User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "get_full_name", "email", "user_type", "is_active", "created_at")
    list_filter = ("user_type", "is_active", "created_at")
    search_fields = ("username", "email", "first_name", "last_name", "phone_number")


@admin.register(models.UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "employee_id", "department", "designation", "date_of_joining", "salary")
    search_fields = ("user__username", "employee_id", "department", "designation")


# ==========================
# PATIENT MANAGEMENT
# ==========================
@admin.register(models.Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("file_number", "name", "phone_number", "city", "balance", "is_active")
    list_filter = ("is_active", "gender", "created_at")
    search_fields = ("name", "file_number", "phone_number", "email", "city", "district")


@admin.register(models.PatientMedicalHistory)
class PatientMedicalHistoryAdmin(admin.ModelAdmin):
    list_display = ("patient", "hypertension", "diabetes", "thyroid_disorder", "autoimmune_disease", "allergies")


# ==========================
# CONSULTATIONS & TREATMENT
# ==========================
@admin.register(models.HairConsultation)
class HairConsultationAdmin(admin.ModelAdmin):
    list_display = ("patient", "consultation_date", "doctor", "scalp_condition", "pull_test")
    list_filter = ("scalp_condition", "pull_test", "consultation_date")
    search_fields = ("patient__name", "doctor__username")


@admin.register(models.ConsultationPhoto)
class ConsultationPhotoAdmin(admin.ModelAdmin):
    list_display = ("consultation", "photo_type", "taken_at")


@admin.register(models.TreatmentPlan)
class TreatmentPlanAdmin(admin.ModelAdmin):
    list_display = ("consultation", "procedure", "total_sessions", "total_cost", "created_by")
    list_filter = ("procedure", "created_at")
    search_fields = ("consultation__patient__name", "procedure__name")



@admin.register(models.TreatmentSession)
class TreatmentSessionAdmin(admin.ModelAdmin):
    list_display = ("appointment", "treatment_plan", "session_number", "performed_by")
    list_filter = ("created_at",)
    search_fields = ("appointment__patient__name",)


# ==========================
# BRANCHES
# ==========================
@admin.register(models.Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "phone_number", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "phone_number", "email")

    def has_module_permission(self, request):
        return (
            request.user.is_superuser or
            in_group(request.user, "OperationsManager") or
            in_group(request.user, "Doctor") or
            request.user.has_perm("core.view_lead")
        )

    def has_view_permission(self, request, obj=None):
        return (
            request.user.is_superuser or
            in_group(request.user, "OperationsManager") or
            in_group(request.user, "Doctor") or
            request.user.has_perm("core.view_lead")
        )

    def has_add_permission(self, request):
        return (
            request.user.is_superuser or
            in_group(request.user, "OperationsManager") or
            in_group(request.user, "Doctor") or
            request.user.has_perm("core.add_lead")
        )

    def has_change_permission(self, request, obj=None):
        return (
            request.user.is_superuser or
            in_group(request.user, "CRO") or
            in_group(request.user, "Receptionist") or
            request.user.has_perm("core.change_lead")
        )

    def has_delete_permission(self, request, obj=None):
        return (
            request.user.is_superuser or
            in_group(request.user, "CRO") or
            in_group(request.user, "Receptionist") or
            request.user.has_perm("core.delete_lead")
        )


# ==========================
# APPOINTMENTS
# ==========================
@admin.register(models.Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("appointment_date", "patient", "branch", "status", "assigned_doctor", "created_by")
    list_filter = ("status", "appointment_date", "branch")
    search_fields = ("patient__name", "patient__phone_number", "branch__name")

    def has_change_permission(self, request, obj=None):
        if (
            in_group(request.user, 'CRO') or
            in_group(request.user, 'Receptionist') or
            in_group(request.user, 'OperationsManager') or
            in_group(request.user, 'Doctor')
        ):
            return True
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if in_group(request.user, 'Receptionist'):
            return False
        return super().has_delete_permission(request, obj)


@admin.register(models.AppointmentLog)
class AppointmentLogAdmin(admin.ModelAdmin):
    list_display = ("appointment", "action", "by", "at", "from_status", "to_status")
    list_filter = ("action", "at")


# ==========================
# FOLLOW-UP
# ==========================
@admin.register(models.FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ("patient", "followup_date", "overall_response_percentage", "patient_satisfaction")
    list_filter = ("followup_date", "created_by")


@admin.register(models.ProgressPhoto)
class ProgressPhotoAdmin(admin.ModelAdmin):
    list_display = ("patient", "photo_type", "taken_date")


# ==========================
# PHARMACY / INVENTORY
# ==========================
@admin.register(models.MedicineCategory)
class MedicineCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")


@admin.register(models.Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = ("name", "generic_name", "medicine_type", "selling_price", "is_active")
    list_filter = ("medicine_type", "is_active")
    search_fields = ("name", "generic_name", "manufacturer")


@admin.register(models.MedicineStock)
class MedicineStockAdmin(admin.ModelAdmin):
    readonly_fields = ("current_quantity", "reserved_quantity", "last_updated")
    list_display = ("medicine", "current_quantity", "reserved_quantity", "is_low_stock")


@admin.register(models.StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ("medicine", "transaction_type", "quantity", "batch_number", "created_at", "created_by")
    list_filter = ("transaction_type", "created_at")
    search_fields = ("medicine__name", "batch_number")


# ==========================
# BILLING & PAYMENTS
# ==========================
@admin.register(models.Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ("bill_number", "patient", "bill_type", "total_amount", "paid_amount", "bill_date")
    list_filter = ("bill_type", "bill_date")
    search_fields = ("bill_number", "patient__name")


@admin.register(models.BillItem)
class BillItemAdmin(admin.ModelAdmin):
    list_display = ("bill", "kind", "description", "quantity", "unit_price", "total_price")
    list_filter = ("kind",)


@admin.register(models.Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("patient", "bill", "amount", "method", "date", "received_by")
    list_filter = ("method", "date")
    search_fields = ("patient__name", "bill__bill_number")


@admin.register(models.Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "default_price", "is_active", "created_at")
    search_fields = ("name", "description")
    list_filter = ("is_active",)
    readonly_fields = ("created_at", "id")
    ordering = ("name",)

    def has_view_permission(self, request, obj=None):
        return (
            request.user.is_superuser or 
            in_group(request.user, 'OperationsManager') or
            in_group(request.user, 'Doctor') or
            in_group(request.user, 'CRO') or
            request.user.has_perm('core.view_service')
        )

    def has_add_permission(self, request):
        return (
            request.user.is_superuser or 
            in_group(request.user, 'OperationsManager') or
            in_group(request.user, 'Doctor') or
            request.user.has_perm('core.add_service')
        )

    def has_change_permission(self, request, obj=None):
        return (
            request.user.is_superuser or 
            in_group(request.user, 'OperationsManager') or
            request.user.has_perm('core.change_service')
        )

    def has_delete_permission(self, request, obj=None):
        return (
            request.user.is_superuser or 
            in_group(request.user, 'OperationsManager') or
            request.user.has_perm('core.delete_service')
        )


# ==========================
# LEAD MANAGEMENT
# ==========================
@admin.register(models.LeadSource)
class LeadSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")




@admin.register(models.Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("name", "phone_number", "lead_source", "priority", "created_at", "created_by")
    list_filter = ("priority", "lead_source", "created_at")
    search_fields = ("name", "phone_number", "email")
    actions = ["convert_selected_leads"]


    def has_module_permission(self, request):
        return (
            request.user.is_superuser or
            in_group(request.user, "CRO") or
            in_group(request.user, "Receptionist") or
            request.user.has_perm("core.view_lead")
        )

    def has_view_permission(self, request, obj=None):
        return (
            request.user.is_superuser or
            in_group(request.user, "CRO") or
            in_group(request.user, "Receptionist") or
            request.user.has_perm("core.view_lead")
        )

    def has_add_permission(self, request):
        return (
            request.user.is_superuser or
            in_group(request.user, "CRO") or
            in_group(request.user, "Receptionist") or
            request.user.has_perm("core.add_lead")
        )

    def has_change_permission(self, request, obj=None):
        return (
            request.user.is_superuser or
            in_group(request.user, "CRO") or
            in_group(request.user, "Receptionist") or
            request.user.has_perm("core.change_lead")
        )

    def has_delete_permission(self, request, obj=None):
        return (
            request.user.is_superuser or
            in_group(request.user, "CRO") or
            in_group(request.user, "Receptionist") or
            request.user.has_perm("core.delete_lead")
        )

    def convert_selected_leads(self, request, queryset):
        count = 0
        for lead in queryset:
            lead.convert_to_patient(registered_by=request.user)
            count += 1
        self.message_user(request, f"Converted {count} lead(s) to patient(s).")
    convert_selected_leads.short_description = "Convert selected leads to patients"

    


# ==========================
# EXPENSE MANAGEMENT
# ==========================
@admin.register(models.ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")


@admin.register(models.Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("expense_number", "category", "amount", "expense_date", "status", "requested_by")
    list_filter = ("status", "expense_date")
    search_fields = ("expense_number", "description", "vendor_name")


# ==========================
# REPORTING
# ==========================
@admin.register(models.DailyReport)
class DailyReportAdmin(admin.ModelAdmin):
    list_display = ("report_date", "new_patients", "total_appointments", "total_revenue", "outstanding_amount")
    list_filter = ("report_date",)
