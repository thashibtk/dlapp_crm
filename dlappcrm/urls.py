from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from core import views as v

urlpatterns = [
    path('admin/', admin.site.urls),

    # auth
    path('login/',  auth_views.LoginView.as_view(template_name='auth/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    #me
    path("me/", v.my_profile, name="my_profile"),
    path("me/password/", v.my_profile_password, name="my_profile_password"),

    # dashboard
    path('', v.dashboard, name='home'),
    path('dashboard/', v.dashboard, name='dashboard'),

    # patients
    path('patients/', v.patient_list, name='patient_list'),
    path('patients/new/', v.patient_create, name='patient_create'),
    path('patients/<uuid:pk>/edit/', v.patient_update, name='patient_update'),
    path('patients/<uuid:pk>/', v.patient_detail, name='patient_detail'),

    # medical history
    path('patients/<uuid:patient_id>/history/new/', v.medical_history_create, name='medical_history_create'),
    path('patients/<uuid:patient_id>/history/edit/', v.medical_history_update, name='medical_history_update'),

    # consultations & plan
    path('patients/<uuid:patient_id>/consultations/new/', v.consultation_create, name='consultation_create'),
    path('consultations/<uuid:pk>/plan/new/', v.treatment_plan_create, name='treatment_plan_create'),
    path('consultations/<uuid:pk>/plan/edit/', v.treatment_plan_update, name='treatment_plan_update'),
    path('consultations/<uuid:pk>/', v.consultation_detail, name='consultation_detail'),
    path('consultations/<uuid:pk>/edit/', v.consultation_edit, name='consultation_edit'),
    path('consultations/<uuid:pk>/photos/new/', v.consultation_photo_create, name='consultation_photo_create'),

    # followups & photos
    path('patients/<uuid:patient_id>/followups/new/', v.followup_create, name='followup_create'),
    path('followups/<uuid:pk>/edit/', v.followup_update, name='followup_update'),
    path('patients/<uuid:patient_id>/photos/new/', v.progress_photo_create, name='progress_photo_create'),

    # appointments
    path('appointments/', v.appointment_list, name='appointment_list'),
    path('appointments/new/', v.appointment_create, name='appointment_create'),
    path('appointments/<uuid:pk>/status/', v.appointment_update_status, name='appointment_update_status'),
    path('appointments/<uuid:pk>/', v.appointment_detail, name='appointment_detail'),
    path('appointments/<uuid:pk>/edit/', v.appointment_edit, name='appointment_edit'),

    path('appointments/<uuid:pk>/reschedule/', v.appointment_reschedule, name='appointment_reschedule'),
    path("appointments/mine/", v.my_appointment_list, name="my_appointment_list"),

    # billing
    path('bills/service/',  v.service_bill_list,  name='service_bill_list'),
    path('bills/pharmacy/', v.pharmacy_bill_list, name='pharmacy_bill_list'),
    path('bills/new/service/', v.service_bill_create, name='service_bill_create'),
    path('bills/new/pharmacy/', v.pharmacy_bill_create, name='pharmacy_sale_create'), 
    path('bills/<uuid:pk>/edit/service/', v.service_bill_edit, name='service_bill_edit'),
    path('bills/<uuid:pk>/edit/pharmacy/', v.pharmacy_bill_edit, name='pharmacy_sale_edit'),    
    path('bills/<uuid:pk>/receipt/', v.bill_receipt, name='bill_receipt'),
     path("api/patients/<uuid:patient_id>/bills/", v.patient_previous_bills, name="patient_previous_bills"),




    # pharmacy
    path('pharmacy/medicines/', v.medicine_list, name='pharmacy_medicine_list'),
    path('pharmacy/medicines/new/', v.medicine_create, name='pharmacy_medicine_create'),
    path('pharmacy/medicines/<uuid:pk>/', v.pharmacy_medicine_detail, name='pharmacy_medicine_detail'),
    path('pharmacy/medicines/<uuid:pk>/edit/', v.pharmacy_medicine_edit, name='pharmacy_medicine_edit'),
    path('pharmacy/stock/', v.pharmacy_stock_list, name='pharmacy_stock_list'),
    path('pharmacy/stock/<uuid:pk>/adjust/', v.pharmacy_stock_adjust, name='pharmacy_stock_adjust'),
    path('pharmacy/transactions/', v.stock_tx_list, name='pharmacy_tx_list'),
    path('pharmacy/transactions/new/', v.stock_tx_create, name='pharmacy_tx_create'),

    path('pharmacy/tx/<uuid:pk>/', v.pharmacy_tx_detail, name='pharmacy_tx_detail'),
    path('pharmacy/tx/<uuid:pk>/edit/', v.pharmacy_tx_edit, name='pharmacy_tx_edit'),

    # Finance report
    path('reports/finance/', v.finance_report, name='finance_report'),

    # leads
    path('leads/', v.lead_list, name='lead_list'),
    path('leads/new/', v.lead_create, name='lead_create'),
    path('leads/<uuid:pk>/', v.lead_detail, name='lead_detail'),
    path('leads/<uuid:pk>/edit/', v.lead_update, name='lead_update'),
    path('leads/<uuid:pk>/convert/', v.lead_convert, name='lead_convert'),
    path('expenses/<uuid:pk>/', v.expense_detail, name='expense_detail'),
    path('expenses/<uuid:pk>/edit/', v.expense_update, name='expense_update'),


    # expenses
    path('expenses/', v.expense_list, name='expense_list'),
    path('expenses/new/', v.expense_create, name='expense_create'),
    path('expenses/<uuid:pk>/approve/', v.expense_approve, name='expense_approve'),
    path('expenses/<uuid:pk>/reject/', v.expense_reject, name='expense_reject'),
    path('expenses/<uuid:pk>/mark-paid/', v.expense_mark_paid, name="expense_mark_paid"),

    #staffs
    path('staff/', v.staff_list, name='staff_list'),
    path('staff/new/', v.staff_create, name='staff_create'),
    path('staff/<pk>/edit/', v.staff_edit, name='staff_edit'),

]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
