from django.contrib import admin
from .models import Bill, BillItem, MedicineStock, StockTransaction, Service, Lead, Appointment
from . import models
from django.contrib.auth.models import Group

def in_group(user, name):
    return user.is_superuser or user.groups.filter(name=name).exists()

admin.site.register(models.User)
admin.site.register(models.UserProfile)
admin.site.register(models.Patient)
admin.site.register(models.PatientMedicalHistory)
admin.site.register(models.HairConsultation)
admin.site.register(models.ConsultationPhoto)
admin.site.register(models.TreatmentPlan)

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('appointment_date', 'patient', 'status', 'assigned_doctor', 'created_by')
    list_filter = ('status', 'appointment_date')
    search_fields = ('patient__name', 'patient__phone_number')

    def has_change_permission(self, request, obj=None):
        if in_group(request.user, 'CRO') or in_group(request.user, 'Receptionist') \
           or in_group(request.user, 'OperationsManager') or in_group(request.user, 'Doctor'):
            return True
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if in_group(request.user, 'Receptionist'):
            return False
        return super().has_delete_permission(request, obj)

admin.site.register(models.TreatmentSession)
admin.site.register(models.FollowUp)
admin.site.register(models.ProgressPhoto)
admin.site.register(models.MedicineCategory)
admin.site.register(models.Medicine)

@admin.register(MedicineStock)
class MedicineStockAdmin(admin.ModelAdmin):
    readonly_fields = ('current_quantity', 'reserved_quantity', 'last_updated')

@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ('medicine', 'transaction_type', 'quantity', 'created_at', 'created_by')


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "default_price", "is_active", "created_at")
    search_fields = ("name", "description")
    list_filter = ("is_active",)
    readonly_fields = ("created_at", "id")
    ordering = ("name",)
    
    def has_module_permission(self, request):
        # Allow superusers and specific groups to see the Service module
        return (
            request.user.is_superuser or 
            in_group(request.user, 'OperationsManager') or
            in_group(request.user, 'Doctor') or
            request.user.has_perm('core.view_service')
        )
    
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

admin.site.register(models.LeadSource)

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    actions = ['convert_selected_leads']

    def convert_selected_leads(self, request, queryset):
        count = 0
        for lead in queryset:
            lead.convert_to_patient(registered_by=request.user)
            count += 1
        self.message_user(request, f"Converted {count} lead(s) to patient(s).")

admin.site.register(models.ExpenseCategory)
admin.site.register(models.Expense)
admin.site.register(models.DailyReport)
admin.site.register(models.AppointmentSlot)
