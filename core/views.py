import logging
from datetime import datetime, date, time, timedelta
from uuid import uuid4
from django.forms import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Sum, OuterRef, Subquery, DateField, CharField, Value, Case, When
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, F
from django.http import HttpResponseBadRequest, JsonResponse
from decimal import Decimal

from .decorators import group_required
from .models import (
    AppointmentLog, MedicineCategory, Patient, PatientMedicalHistory, HairConsultation, Payment, TreatmentPlan,
    FollowUp, ProgressPhoto, Appointment, Bill, Branch,
    Medicine, MedicineStock, StockTransaction,
    Lead, LeadSource, Expense, BillItem, User
)
from .forms import (
    STAFFABLE_USER_TYPES, AppointmentCreateForm, AppointmentEditForm, AppointmentRescheduleForm, BillHeaderForm, PatientForm,
    PatientMedicalHistoryForm, HairConsultationForm, ServiceBillItemFormSet, StaffCreateForm, StaffEditForm, StockAdjustForm, TreatmentPlanForm,
    FollowUpForm, ProgressPhotoForm,
    MedicineForm, StockTransactionForm,
    LeadForm, LeadConvertForm,
    ExpenseForm, ConsultationPhotoForm, PharmacyBillItemFormSet, user_can_edit_status
)

from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import authenticate, login, logout

DOCTOR_USER_TYPES = {'doctor', 'consulting_doctor'}





def _normalize_to_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value

def _ensure_aware(dt):
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt

def _aware_start_of_day(value):
    value = _normalize_to_date(value)
    if value is None:
        return None
    return _ensure_aware(datetime.combine(value, time.min))

def _aware_start_of_next_day(value):
    value = _normalize_to_date(value)
    if value is None:
        return None
    return _ensure_aware(datetime.combine(value + timedelta(days=1), time.min))

def apply_date_range(queryset, field_name, start=None, end=None):
    start_dt = _aware_start_of_day(start)
    if start_dt:
        queryset = queryset.filter(**{f"{field_name}__gte": start_dt})
    end_dt = _aware_start_of_next_day(end)
    if end_dt:
        queryset = queryset.filter(**{f"{field_name}__lt": end_dt})
    return queryset


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
            return redirect("dashboard")
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, "auth/login.html")

def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect("login")

@login_required
def my_profile(request):
    
    profile = getattr(request.user, "profile", None)
    ctx = {
        "u": request.user,
        "profile": profile,
    }
    return render(request, "accounts/profile.html", ctx)


@login_required
def my_profile_password(request):
    if request.method == "POST":
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # keep user logged in
            messages.success(request, "Password updated successfully.")
            return redirect("my_profile")
        messages.error(request, "Please fix the errors below.")
    else:
        form = PasswordChangeForm(user=request.user)

    # Add bootstrap classes without touching the built-in form
    for f in form.fields.values():
        css = f.widget.attrs.get("class", "")
        if getattr(f.widget, "input_type", "") in ("password", "text") or f.widget.__class__.__name__ == "PasswordInput":
            f.widget.attrs["class"] = (css + " form-control").strip()
    return render(request, "accounts/password_change.html", {"form": form})


# ---------------- Dashboard ----------------
@group_required('PharmacyManager','OperationsManager','Doctor','ConsultingDoctor','Receptionist','Staff','CRO')
def dashboard(request):
    today = timezone.localdate()
    range_param = (request.GET.get('range') or '').strip()
    start_str = request.GET.get('from') or request.GET.get('start') or request.GET.get('date')
    end_str = request.GET.get('to') or request.GET.get('end')

    def parse_iso(value):
        try:
            return date.fromisoformat(value) if value else None
        except ValueError:
            return None

    # Default to today if no range/date provided
    if not range_param and not start_str and not end_str:
        start = end = today
        range_param = 'today'
    elif range_param:
        if range_param == 'today':
            start = end = today
        elif range_param == 'yesterday':
            start = today - timedelta(days=1)
            end = start
        elif range_param == '7d':
            start = today - timedelta(days=6)
            end = today
        elif range_param == 'month':
            start = today.replace(day=1)
            if today.month == 12:
                end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        else:
            start = parse_iso(start_str)
            end = parse_iso(end_str)
    else:
        start = parse_iso(start_str)
        end = parse_iso(end_str)

    if start and end and end < start:
        start, end = end, start

    def _format_range_label(rng, dfrom, dto):
        if not dfrom and not dto:
            return "All Time"
        if not dfrom:
            dfrom = dto
        if not dto:
            dto = dfrom

        if rng == 'today':
            return "Today"
        if rng == 'yesterday':
            return "Yesterday"
        if rng == '7d':
            return "Last 7 days"
        if rng == 'month':
            return "This month"

        if dfrom == dto:
            return dfrom.strftime("%d %b %Y")
        if dfrom.year == dto.year:
            if dfrom.month == dto.month:
                return f"{dfrom.strftime('%d')}-{dto.strftime('%d %b %Y')}"
            return f"{dfrom.strftime('%d %b')} - {dto.strftime('%d %b %Y')}"
        return f"{dfrom.strftime('%d %b %Y')} - {dto.strftime('%d %b %Y')}"

    def _kpi_day_label(rng, dfrom, dto):
        if not dfrom and not dto:
            return "All Time"
        if rng == 'today':
            return "Today"
        if rng == 'yesterday':
            return "Yesterday"
        if rng == '7d':
            return "Last 7 days"
        if rng == 'month':
            return "This month"
        return _format_range_label(rng, dfrom, dto)

    def _kpi_billed_label(rng, dfrom, dto):
        base = _format_range_label(rng, dfrom, dto)
        if rng == 'month' and not (start_str or end_str):
            return "This Month Billed"
        return f"Billed - {base}"

    kpi_range_label = _format_range_label(range_param, start, end)
    kpi_day_label = _kpi_day_label(range_param, start, end)
    kpi_billed_lbl = _kpi_billed_label(range_param, start, end)

    appointments_in_range = apply_date_range(Appointment.objects.all(), 'appointment_date', start, end)
    today_appts = appointments_in_range.count()

    bills_in_range = apply_date_range(Bill.objects.all(), 'bill_date', start, end)
    today_collection = bills_in_range.aggregate(s=Coalesce(Sum('paid_amount'), Decimal('0.00')))['s']
    month_billed = bills_in_range.aggregate(s=Coalesce(Sum('total_amount'), Decimal('0.00')))['s']

    outstanding_balance = Bill.objects.aggregate(
        s=Coalesce(Sum(F('total_amount') - F('paid_amount')), Decimal('0.00'))
    )['s']

    is_doctor = request.user.groups.filter(name__in=["Doctor", "ConsultingDoctor"]).exists()
    my_appts_count = 0
    if is_doctor:
        my_appts_count = apply_date_range(
            Appointment.objects.filter(assigned_doctor_id=request.user.id),
            'appointment_date',
            start,
            end,
        ).count()

    low_stock_qs = (
        MedicineStock.objects
        .select_related('medicine')
        .filter(current_quantity__lte=F('medicine__minimum_stock_level'))
    )
    low_stock_count = low_stock_qs.count()

    pending_exp_qs = Expense.objects.filter(status='pending')
    pending_exp_count = pending_exp_qs.count()
    pending_exp_amount = pending_exp_qs.aggregate(
        s=Coalesce(Sum('amount'), Decimal('0.00'))
    )['s']

    leads_in_range = apply_date_range(Lead.objects.all(), 'created_at', start, end)
    total_leads = leads_in_range.count()
    converted_count = leads_in_range.filter(converted_patient__isnull=False).count()
    conversion_rate = round((converted_count / total_leads) * 100, 1) if total_leads else 0.0

    now_dt = timezone.now()

    upcoming = (
        apply_date_range(
            Appointment.objects.select_related('patient', 'assigned_doctor', 'branch'),
            'appointment_date',
            today,
            today,
        )
        .filter(appointment_date__gte=now_dt)
        .order_by('appointment_date')[:8]
    )

    recent_bills = (
        Bill.objects
        .select_related('patient')
        .order_by('-bill_date')[:8]
    )

    low_stock = low_stock_qs.order_by('current_quantity')[:8]

    recent_leads = (
        Lead.objects
        .select_related('lead_source')
        .order_by('-created_at')[:8]
    )

    if not range_param and not start_str and not end_str:
        chart_start = today - timedelta(days=9)
        chart_end = today
    else:
        chart_start = start
        chart_end = end
        if chart_start and not chart_end:
            chart_end = chart_start
        elif chart_end and not chart_start:
            chart_start = chart_end
        if not chart_start:
            chart_start = today - timedelta(days=9)
        if not chart_end:
            chart_end = today

    if chart_end < chart_start:
        chart_start, chart_end = chart_end, chart_start

    max_days = 31
    span = (chart_end - chart_start).days
    if span > max_days - 1:
        start_for_chart = chart_end - timedelta(days=max_days - 1)
    else:
        start_for_chart = chart_start

    day_count = (chart_end - start_for_chart).days + 1
    days = [start_for_chart + timedelta(days=i) for i in range(day_count)]
    rev_labels = [d.strftime('%d %b') for d in days]
    rev_values = []
    for d in days:
        v = apply_date_range(Bill.objects.all(), 'bill_date', d, d).aggregate(
            s=Coalesce(Sum('paid_amount'), Decimal('0.00'))
        )['s']
        rev_values.append(float(v))

    chart_revenue = {'labels': rev_labels, 'values': rev_values}
    chart_leads = {
        'open': Lead.objects.filter(converted_patient__isnull=True).count(),
        'converted': Lead.objects.filter(converted_patient__isnull=False).count()
    }

    ctx = {
        'summary': {
            'today_appts': today_appts,
            'today_collection': today_collection,
            'month_billed': month_billed,
            'outstanding_balance': outstanding_balance,
            'low_stock_count': low_stock_count,
            'pending_exp_count': pending_exp_count,
            'pending_exp_amount': pending_exp_amount,
            'open_leads_count': Lead.objects.filter(converted_patient__isnull=True).count(),
            'conversion_rate': conversion_rate,
            'my_appts_count': my_appts_count,
        },
        'upcoming': upcoming,
        'recent_bills': recent_bills,
        'low_stock': low_stock,
        'recent_leads': recent_leads,
        'chart_revenue': chart_revenue,
        'chart_leads': chart_leads,
        'selected': {
            'from': start,
            'to': end,
            'range': range_param,
        },
        'kpi_range_label': kpi_range_label,
        'kpi_day_label': kpi_day_label,
        'kpi_billed_label': kpi_billed_lbl,
    }
    return render(request, 'dashboard.html', ctx)

# ---------------- Patients ----------------
@group_required('Receptionist','CRO','OperationsManager','Doctor','ConsultingDoctor','PharmacyManager','Staff')
def patient_list(request):
    # ---- Parse date filters (registered date) ----
    today = timezone.localdate()

    def parse_iso(d, default=None):
        if isinstance(d, date):
            return d
        try:
            return date.fromisoformat(d) if d else default
        except (TypeError, ValueError):
            return default
            
    today_date = timezone.localdate()
    tomorrow_date = today_date + timedelta(days=1)

    start_raw = request.GET.get('from')
    end_raw = request.GET.get('to')
    start = parse_iso(start_raw)
    end = parse_iso(end_raw)

    if end and start and end < start:
        start, end = end, start

    qs = Patient.objects.all()
    qs = apply_date_range(qs, 'created_at', start, end)

    # ---- Annotate next follow-up per patient (DateField-aware) ----
    upcoming_sub = (FollowUp.objects
        .filter(
            patient=OuterRef('pk'),
            next_followup_date__isnull=False,
            next_followup_date__gte=today_date,
        )
        .order_by('next_followup_date')
        .values('next_followup_date')[:1])

    latest_past_sub = (FollowUp.objects
        .filter(
            patient=OuterRef('pk'),
            next_followup_date__lt=today_date,
            next_followup_date__isnull=False,
        )
        .order_by('-next_followup_date')
        .values('next_followup_date')[:1])
    
    # Annotate 'next_fu' and then determine its status
    qs = (qs
        .annotate(upcoming_fu=Subquery(upcoming_sub, output_field=DateField()))
        .annotate(latest_past_fu=Subquery(latest_past_sub, output_field=DateField()))
        .annotate(next_fu=Coalesce('upcoming_fu', 'latest_past_fu'))
        .annotate(
            status=Case(
                When(next_fu__isnull=False, then=Case(
                    When(next_fu=today_date, then=Value('today')),
                    When(next_fu=tomorrow_date, then=Value('tomorrow')),
                    When(next_fu__lt=today_date, then=Value('overdue')),
                    default=Value('upcoming'),
                )),
                default=Value('none'),
                output_field=CharField()
            )
        ))

    # ---- Filter by balance status (CORRECTED LOGIC) ----
    balance_status = request.GET.get('balance_status')

    # Sum up all 'due' and 'advance' amounts for a patient across all bills
    # Uses Case, When, and F expressions to calculate dynamically
    bill_subquery = Bill.objects.filter(patient=OuterRef('pk')).values('patient').annotate(
        total_due_calc=Sum(Case(
            When(total_amount__gt=F('paid_amount'), then=F('total_amount') - F('paid_amount')),
            default=Value(0),
            output_field=DecimalField()
        )),
        total_advance_calc=Sum(Case(
            When(paid_amount__gt=F('total_amount'), then=F('paid_amount') - F('total_amount')),
            default=Value(0),
            output_field=DecimalField()
        ))
    )

    qs = qs.annotate(
        total_due=Coalesce(Subquery(bill_subquery.values('total_due_calc'), output_field=DecimalField()), Decimal('0.00')),
        total_advance=Coalesce(Subquery(bill_subquery.values('total_advance_calc'), output_field=DecimalField()), Decimal('0.00'))
    )

    if balance_status == 'due':
        qs = qs.filter(total_due__gt=0)
    elif balance_status == 'advance':
        qs = qs.filter(total_advance__gt=0)
    elif balance_status == 'settled':
        # Settled means no due and no advance
        qs = qs.filter(total_due=0, total_advance=0)

    # Order by creation date
    qs = qs.order_by('-created_at')

    ctx = {
        'patients': qs,
        'selected': {
            'from': start, 
            'to': end,
            'balance_status': balance_status, # Pass the selected status to the template
        },
        'today_date': today_date,
    }
    return render(request, 'patients/list.html', ctx)


@group_required('Receptionist','OperationsManager','Doctor','CRO')
def patient_create(request):
    if request.method == 'POST':
        form = PatientForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.registered_by = request.user
            obj.save()
            messages.success(request, f"Patient {obj.name} registered.")
            return redirect('patient_list')
    else:
        form = PatientForm()
    return render(request, 'patients/form.html', {'form': form})

@group_required('Receptionist','CRO','OperationsManager','Doctor','ConsultingDoctor','PharmacyManager','Staff')
def patient_update(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    if request.method == 'POST':
        form = PatientForm(request.POST, instance=patient)
        if form.is_valid():
            form.save()
            messages.success(request, "Patient updated.")
            return redirect('patient_detail', pk=patient.pk)
    else:
        form = PatientForm(instance=patient)
    # re-use your patient form template, just tell it we’re editing
    return render(request, 'patients/form.html', {'form': form, 'is_edit': True, 'patient': patient})

@group_required('Receptionist','Doctor','ConsultingDoctor','OperationsManager','PharmacyManager','CRO','Staff')
def patient_detail(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    ctx = {
        'patient': patient,
        'history': getattr(patient, 'medical_history', None),
        'consultations': patient.consultations.select_related('doctor').order_by('-consultation_date'),
        'followups': patient.followups.select_related('treatment_plan').order_by('-followup_date'),
        'photos': ProgressPhoto.objects.filter(patient=patient).order_by('-taken_date'),
        'appointments': patient.appointments.select_related('assigned_doctor').order_by('-appointment_date'),
        'bills': patient.bills.order_by('-bill_date'),
        'billing_summary': {'total_billed': patient.bills.aggregate(s=Sum('total_amount'))['s'] or 0},
    }
    return render(request, 'patients/detail.html', ctx)

# ---------------- Medical History ----------------
@group_required('Doctor','ConsultingDoctor','Receptionist','OperationsManager')
def medical_history_create(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    # If already exists, go to edit
    if hasattr(patient, 'medical_history'):
        return redirect('medical_history_update', patient_id=patient.pk)

    form = PatientMedicalHistoryForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        mh = form.save(commit=False)
        mh.patient = patient
        mh.save()
        messages.success(request, "Medical history saved.")
        return redirect('patient_detail', pk=patient.pk, fragment='history')

    return render(
        request,
        'patients/medical_history_form.html',
        {
            'form': form,
            'patient': patient,   # <-- pass patient
            'is_edit': False,     # <-- for header/buttons
        }
    )

@group_required('Doctor','ConsultingDoctor','Receptionist','OperationsManager')
def medical_history_update(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    mh = get_object_or_404(PatientMedicalHistory, patient=patient)

    form = PatientMedicalHistoryForm(request.POST or None, instance=mh)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Medical history updated.")
        return redirect('patient_detail', pk=patient.pk)

    return render(
        request,
        'patients/medical_history_form.html',
        {
            'form': form,
            'patient': patient,   # <-- pass patient
            'is_edit': True,      # <-- for header/buttons
        }
    )

# ---------------- Consultations ----------------

@group_required('Doctor','ConsultingDoctor','OperationsManager','Receptionist','PharmacyManager','Staff','CRO')
def consultation_detail(request, pk):
    c = get_object_or_404(HairConsultation.objects.select_related('patient','doctor'), pk=pk)
    plan = getattr(c, 'treatment_plan', None)
    photos = c.photos.all().order_by('photo_type', 'taken_at')
    return render(request, 'consultations/detail.html', {
        'c': c, 'patient': c.patient, 'plan': plan, 'photos': photos,
    })

@group_required('Doctor','ConsultingDoctor','OperationsManager')
def consultation_create(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    if request.method == 'POST':
        form = HairConsultationForm(request.POST, request.FILES)
        if form.is_valid():
            c = form.save(commit=False)
            c.patient = patient
            # If doctor not chosen, default to current user if they are a doctor
            if not c.doctor and getattr(request.user, 'user_type', '') in DOCTOR_USER_TYPES:
                c.doctor = request.user
            c.save()
            messages.success(request, "Consultation created.")
            return redirect('patient_detail', pk=patient.pk)
    else:
        initial = {}
        if getattr(request.user, 'user_type', '') in DOCTOR_USER_TYPES:
            initial['doctor'] = request.user
        form = HairConsultationForm(initial=initial)
    return render(request, 'consultations/form.html', {
        'form': form, 'patient': patient, 'is_edit': False
    })

@group_required('Doctor','ConsultingDoctor','OperationsManager')
def consultation_edit(request, pk):
    c = get_object_or_404(HairConsultation, pk=pk)
    if request.method == 'POST':
        form = HairConsultationForm(request.POST, request.FILES, instance=c)
        if form.is_valid():
            form.save()
            messages.success(request, "Consultation updated.")
            return redirect('consultation_detail', pk=c.pk)
    else:
        form = HairConsultationForm(instance=c)
    return render(request, 'consultations/form.html', {
        'form': form, 'patient': c.patient, 'is_edit': True, 'c': c
    })

@group_required('Doctor','ConsultingDoctor','OperationsManager','PharmacyManager','Receptionist')
def consultation_photo_create(request, pk):
    c = get_object_or_404(HairConsultation, pk=pk)
    if request.method == 'POST':
        form = ConsultationPhotoForm(request.POST, request.FILES, consultation=c)
        if form.is_valid():
            cp = form.save(commit=False)
            cp.consultation = c
            cp.save()
            messages.success(request, "Photo added.")
            return redirect('consultation_detail', pk=c.pk)
    else:
        form = ConsultationPhotoForm(consultation=c)
    return render(request, 'consultations/photo_form.html', {'form': form, 'c': c})

# ---------------- Treatment Plan ----------------
@group_required('Doctor','ConsultingDoctor','OperationsManager')
def treatment_plan_create(request, pk):
    consultation = get_object_or_404(HairConsultation, pk=pk)
    if hasattr(consultation, 'treatment_plan'):
        return redirect('treatment_plan_update', pk=pk)

    if request.method == 'POST':
        form = TreatmentPlanForm(request.POST, request.FILES)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.consultation = consultation
            plan.created_by = request.user
            plan.save()
            messages.success(request, "Treatment plan saved.")
            return redirect('patient_detail', pk=consultation.patient.pk)
    else:
        form = TreatmentPlanForm()

    return render(
        request, 'treatments/plan_form.html',
        {'form': form, 'consultation': consultation, 'patient': consultation.patient, 'is_edit': False}
    )

@group_required('Doctor','ConsultingDoctor','OperationsManager')
def treatment_plan_update(request, pk):
    consultation = get_object_or_404(HairConsultation, pk=pk)
    plan = consultation.treatment_plan
    if request.method == 'POST':
        form = TreatmentPlanForm(request.POST, request.FILES, instance=plan)
        if form.is_valid():
            form.save()
            messages.success(request, "Treatment plan updated.")
            return redirect('patient_detail', pk=consultation.patient.pk)
    else:
        form = TreatmentPlanForm(instance=plan)

    return render(
        request, 'treatments/plan_form.html',
        {'form': form, 'consultation': consultation, 'patient': consultation.patient, 'is_edit': True}
    )

# ---------------- Followups & Photos ----------------

@group_required('Doctor','ConsultingDoctor','OperationsManager')
def followup_create(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    latest_plan = (TreatmentPlan.objects
                   .filter(consultation__patient=patient)
                   .order_by('-created_at')
                   .first())

    if request.method == 'POST':
        form = FollowUpForm(request.POST)
        if not latest_plan:
            form.add_error(None, "No treatment plan found for this patient. Create a consultation and treatment plan first.")
        if form.is_valid():
            fu = form.save(commit=False)
            fu.patient = patient
            fu.treatment_plan = latest_plan
            fu.created_by = request.user
            fu.save()
            messages.success(request, "Follow-up recorded.")
            return redirect('patient_detail', pk=patient.pk)
    else:
        form = FollowUpForm(initial={'followup_date': timezone.localdate()})

    return render(request, 'followups/form.html', {
        'form': form,
        'patient': patient,
        'is_edit': False,
    })

@group_required('Doctor','ConsultingDoctor','OperationsManager')
def followup_update(request, pk):
    fu = get_object_or_404(FollowUp.objects.select_related('patient','treatment_plan'), pk=pk)
    patient = fu.patient

    if request.method == 'POST':
        form = FollowUpForm(request.POST, instance=fu)
        if form.is_valid():
            form.save()
            messages.success(request, "Follow-up updated.")
            return redirect('patient_detail', pk=patient.pk)
    else:
        form = FollowUpForm(instance=fu)

    return render(request, 'followups/form.html', {
        'form': form,
        'patient': patient,
        'is_edit': True,
    })

@group_required('Doctor','ConsultingDoctor','OperationsManager','PharmacyManager','Receptionist')
def progress_photo_create(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    if request.method == 'POST':
        form = ProgressPhotoForm(request.POST, request.FILES)
        if form.is_valid():
            pp = form.save(commit=False)
            pp.patient = patient
            pp.save()
            messages.success(request, "Photo added.")
            return redirect('patient_detail', pk=patient.pk)
    else:
        form = ProgressPhotoForm()
    return render(request, 'photos/form.html', {'form': form})

# ---------------- Appointments ----------------

STATUS_CHOICES_UI = [
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
    ('rescheduled', 'Rescheduled'),

]


@group_required('Receptionist', 'CRO', 'OperationsManager', 'Doctor', 'PharmacyManager', 'Staff')
def appointment_list(request):
    q = (request.GET.get('q') or '').strip()
    doctor_id = (request.GET.get('doctor') or '').strip()
    branch_id = (request.GET.get('branch') or 'all').strip()
    status = (request.GET.get('status') or '').strip()
    range_param = request.GET.get('range', '').strip()

    today = timezone.localdate()
    start_str = request.GET.get('from') or request.GET.get('start') or request.GET.get('date')
    end_str   = request.GET.get('to') or request.GET.get('end')

    def parse_iso(d, default=None):
        try:
            return date.fromisoformat(d) if d else default
        except ValueError:
            return default

    # --- Resolve date range ---
    start, end = None, None
    if range_param == 'today':
        start = end = today
    elif range_param == '7d':
        start, end = today - timedelta(days=6), today
    elif range_param == 'month':
        start = today.replace(day=1)
        end = (today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
               if today.month == 12 else
               today.replace(month=today.month + 1, day=1) - timedelta(days=1))
    else:
        start = parse_iso(start_str, None)
        end   = parse_iso(end_str, None)

    # ✅ Default to today if nothing provided
    if not range_param and not start_str and not end_str:
        start = end = today
        range_param = 'today'

    if start and end and end < start:
        start, end = end, start

    qs = Appointment.objects.select_related('patient', 'assigned_doctor', 'branch')
    qs = apply_date_range(qs, 'appointment_date', start, end)

    if q:
        qs = qs.filter(
            Q(patient__name__icontains=q) |
            Q(patient__phone_number__icontains=q) |
            Q(patient__file_number__icontains=q)
        )

    if doctor_id and doctor_id != 'all':
        qs = qs.filter(assigned_doctor_id=doctor_id)

    if branch_id and branch_id != 'all':
        qs = qs.filter(branch_id=branch_id)

    if status and status != 'all':
        qs = qs.filter(status=status)

    qs = qs.order_by('appointment_date')

    doctors = (User.objects
               .filter(is_active=True, user_type__in=DOCTOR_USER_TYPES)
               .order_by('first_name', 'last_name', 'username'))

    branches = Branch.objects.filter(is_active=True).order_by('name')

    ctx = {
        'appointments': qs,
        'doctors': doctors,
        'branches': branches,
        'status_choices': list(STATUS_CHOICES_UI),
        'status_choicesfilter': [('all', 'All'), ('scheduled', 'Scheduled')] + list(STATUS_CHOICES_UI),
        'selected': {
            'from': start,
            'to': end,
            'q': q,
            'doctor': doctor_id,
            'branch': branch_id,
            'status': status or 'all',
            'range': range_param,
        },
    }
    return render(request, 'appointments/list.html', ctx)


@group_required('Doctor','ConsultingDoctor')
def my_appointment_list(request):
    # --- inputs ---
    q           = (request.GET.get('q') or '').strip()
    status      = (request.GET.get('status') or '').strip()
    branch_id   = (request.GET.get('branch') or 'all').strip()
    range_param = (request.GET.get('range') or '').strip()
    today = timezone.localdate()
    start_str = request.GET.get('from') or request.GET.get('start') or request.GET.get('date')
    end_str   = request.GET.get('to')   or request.GET.get('end')

    def parse_iso(d, default=None):
        try:
            return date.fromisoformat(d) if d else default
        except ValueError:
            return default

    # --- resolve date window ---
    start = end = None
    if range_param:
        if range_param == 'today':
            start, end = today, today
        elif range_param == '7d':
            start, end = today - timedelta(days=6), today
        elif range_param == 'month':
            start = today.replace(day=1)
            if today.month == 12:
                end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        else:
            start = parse_iso(start_str)
            end = parse_iso(end_str)
    else:
        start = parse_iso(start_str)
        end = parse_iso(end_str)

    # ✅ Default to today if nothing provided
    if not range_param and not start_str and not end_str:
        start = end = today
        range_param = 'today'

    if end and start and end < start:
        start, end = end, start

    # --- base queryset: ONLY this doctor’s appointments ---
    qs = (Appointment.objects
          .select_related('patient', 'assigned_doctor', 'branch')
          .filter(assigned_doctor=request.user))

    qs = apply_date_range(qs, 'appointment_date', start, end)

    # --- search ---
    if q:
        qs = qs.filter(
            Q(patient__name__icontains=q) |
            Q(patient__phone_number__icontains=q) |
            Q(patient__file_number__icontains=q)
        )

    # --- status ---
    if status and status != 'all':
        qs = qs.filter(status=status)

    if branch_id and branch_id != 'all':
        qs = qs.filter(branch_id=branch_id)

    qs = qs.order_by('appointment_date')

    branches = Branch.objects.filter(is_active=True).order_by('name')

    ctx = {
        'appointments': qs,
        'branches': branches,
        'status_choices': list(STATUS_CHOICES_UI),
        'status_choicesfilter': [('all','All'), ('scheduled','Scheduled')] + list(STATUS_CHOICES_UI),
        'selected': {
            'from': start,
            'to': end,
            'q': q,
            'branch': branch_id,
            'status': status or 'all',
            'range': range_param,
        },
    }
    return render(request, 'appointments/mine.html', ctx)


def log_action(appt, by, action, *, from_status='', to_status='',
               from_dt=None, to_dt=None, note=''):
    AppointmentLog.objects.create(
        appointment=appt,
        by=by if getattr(by, 'pk', None) else None,
        action=action,
        from_status=from_status or '',
        to_status=to_status or '',
        from_datetime=from_dt,
        to_datetime=to_dt,
        note=note or ''
    )


@group_required('Receptionist', 'OperationsManager', 'Doctor','ConsultingDoctor')
def appointment_create(request):
    initial = {}
    pid = request.GET.get('patient')
    if pid:
        try:
            initial['patient'] = Patient.objects.get(pk=pid)
        except Patient.DoesNotExist:
            pass

    if request.method == 'POST':
        form = AppointmentCreateForm(request.POST)
        if form.is_valid():
            appt = form.save(commit=False)
            if not appt.status:
                appt.status = 'scheduled'
            appt.created_by = request.user

            # normalize datetime
            dt = appt.appointment_date
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            appt.appointment_date = dt.replace(second=0, microsecond=0)

            appt.save()

            log_action(
                appt, request.user, 'create',
                to_status=appt.status,
                to_dt=appt.appointment_date
            )

            messages.success(request, "Appointment created.")
            return redirect('appointment_list')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AppointmentCreateForm(initial=initial)

    return render(request, 'appointments/form.html', {'form': form, 'is_edit': False})


@group_required('Receptionist', 'OperationsManager', 'Doctor','ConsultingDoctor')
def appointment_edit(request, pk):
    appt = get_object_or_404(Appointment, pk=pk)
    old_status = appt.status

    if request.method == 'POST':
        form = AppointmentEditForm(request.POST, instance=appt)
        if form.is_valid():
            updated = form.save(commit=False)

            # normalize datetime
            dt = updated.appointment_date
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            updated.appointment_date = dt.replace(second=0, microsecond=0)

            updated.save()

            if 'status' in form.changed_data:
                new_status = updated.status
                if new_status == 'completed':
                    action = 'complete'
                elif new_status == 'cancelled':
                    action = 'cancel'
                else:
                    action = 'reschedule'
                log_action(updated, request.user, action,
                           from_status=old_status, to_status=new_status)

            messages.success(request, "Appointment updated.")
            return redirect('appointment_detail', pk=appt.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AppointmentEditForm(instance=appt)

    return render(request, 'appointments/form.html', {'form': form, 'is_edit': True})


@group_required('Receptionist','OperationsManager','Doctor','ConsultingDoctor')
@transaction.atomic
def appointment_reschedule(request, pk):
    appt = get_object_or_404(Appointment, pk=pk)

    if request.method == 'POST':
        # ✅ capture before binding (important!)
        old_dt = appt.appointment_date  
        old_status = appt.status

        form = AppointmentRescheduleForm(request.POST, instance=appt)
        if form.is_valid():
            # new datetime from form
            new_dt = form.cleaned_data['appointment_date']

            # normalize both to minute precision
            old_norm = old_dt.replace(second=0, microsecond=0)
            new_norm = new_dt.replace(second=0, microsecond=0)

            print(f"DEBUG VIEW: old_norm={old_norm}, new_norm={new_norm}")

            date_changed = (old_norm != new_norm)
            doctor_changed = ('assigned_doctor' in form.changed_data)
            notes_changed = ('notes' in form.changed_data)

            if date_changed:
                # save new values
                new_obj = form.save(commit=False)
                new_obj.appointment_date = new_norm
                new_obj.status = 'rescheduled'

                reason = (form.cleaned_data.get('reschedule_reason') or '').strip()

                if hasattr(new_obj, 'rescheduled_from'):
                    new_obj.rescheduled_from = old_dt
                if hasattr(new_obj, 'rescheduled_at'):
                    new_obj.rescheduled_at = timezone.now()
                if hasattr(new_obj, 'reschedule_reason'):
                    new_obj.reschedule_reason = reason

                new_obj.save()

                log_action(
                    new_obj, request.user, 'reschedule',
                    from_status=old_status, to_status='rescheduled',
                    from_dt=old_norm, to_dt=new_norm, note=reason
                )

                old_local = timezone.localtime(old_norm)
                new_local = timezone.localtime(new_norm)
                messages.success(
                    request,
                    f"Appointment rescheduled from "
                    f"{old_local.strftime('%d-%m-%Y %H:%M')} "
                    f"to {new_local.strftime('%d-%m-%Y %H:%M')}."
                )

            elif doctor_changed or notes_changed:
                new_obj = form.save(commit=False)
                new_obj.appointment_date = old_dt  # keep time unchanged
                fields_to_update = []
                if doctor_changed:
                    fields_to_update.append('assigned_doctor')
                if notes_changed:
                    fields_to_update.append('notes')
                new_obj.save(update_fields=fields_to_update)
                messages.success(request, "Appointment updated.")

            else:
                messages.info(request, "No changes detected.")

            return redirect('appointment_detail', pk=appt.pk)
        else:
            messages.error(request, "Please correct the errors below.")
            print(f"DEBUG VIEW: Form errors: {form.errors}")
    else:
        form = AppointmentRescheduleForm(instance=appt)

    return render(request, 'appointments/reschedule_form.html', {
        'form': form,
        'appt': appt,
        'is_edit': True,
    })

@group_required('Receptionist', 'OperationsManager', 'Doctor','ConsultingDoctor')
def appointment_detail(request, pk):
    appt = get_object_or_404(
        Appointment.objects.select_related(
            'patient', 'assigned_doctor', 'created_by', 'treatment_plan'
        ),
        pk=pk
    )
    status_choices = STATUS_CHOICES_UI
    logs = appt.logs.select_related('by').order_by('-at')
    return render(request, 'appointments/detail.html', {
        'a': appt,
        'status_choices': status_choices,
        'logs': logs,
    })


@group_required('Receptionist', 'OperationsManager', 'Doctor','ConsultingDoctor')
@require_POST
def appointment_update_status(request, pk):
    appt = get_object_or_404(Appointment, pk=pk)
    new_status = (request.POST.get('status') or '').strip()

    valid_statuses = dict(Appointment.STATUS_CHOICES)
    if new_status not in valid_statuses:
        messages.error(request, "Invalid status selection.")
        return redirect(request.META.get('HTTP_REFERER') or 'appointment_detail', pk=appt.pk)

    old_status = appt.status
    if new_status == old_status:
        messages.info(request, "Status unchanged.")
        return redirect(request.META.get('HTTP_REFERER') or 'appointment_detail', pk=appt.pk)

    appt.status = new_status
    appt.save(update_fields=['status'])

    if new_status == 'completed':
        action = 'complete'
    elif new_status == 'cancelled':
        action = 'cancel'
    else:
        action = 'reschedule'

    log_action(
        appt, request.user, action,
        from_status=old_status, to_status=new_status
    )

    messages.success(request, f"Status updated to {valid_statuses[new_status]}.")
    return redirect(request.META.get('HTTP_REFERER') or 'appointment_detail', pk=appt.pk)

# ---------------- Billing ----------------

from django.db.models import Q, F, ExpressionWrapper, DecimalField

BILL_STATUS_CHOICES_UI = [
    ('paid', 'Paid'),
    ('partial', 'Partial'),
    ('unpaid', 'Unpaid'),
]
PAYMENT_METHOD_CHOICES = [
    ('cash', 'Cash'),
    ('card', 'Card'),
    ('upi', 'UPI'),
    ('cheque', 'Cheque'),
]


def _bill_queryset_with_filters(request, bill_type):
    q = (request.GET.get('q') or '').strip()
    payment_method = (request.GET.get('method') or '').strip()
    balance_status = (request.GET.get('balance_status') or '').strip()
    range_param = request.GET.get('range', '').strip()

    today = timezone.localdate()
    start_str = request.GET.get('from') or request.GET.get('start') or request.GET.get('date')
    end_str   = request.GET.get('to') or request.GET.get('end')

    def _parse_iso(d, default=None):
        if isinstance(d, date):
            return d
        try:
            return date.fromisoformat(d) if d else default
        except (TypeError, ValueError):
            return default

    # --- resolve date window ---
    start = end = None
    if range_param:
        if range_param == 'today':
            start, end = today, today
        elif range_param == '7d':
            start, end = today - timedelta(days=6), today
        elif range_param == 'month':
            start = today.replace(day=1)
            if today.month == 12:
                end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        else:
            start = _parse_iso(start_str)
            end = _parse_iso(end_str)
    else:
        start = _parse_iso(start_str)
        end = _parse_iso(end_str)

    # ✅ Default to today if nothing provided
    if not range_param and not start_str and not end_str:
        start = end = today
        range_param = 'today'

    if start and end and end < start:
        start, end = end, start

    qs = (Bill.objects
          .select_related('patient')
          .prefetch_related('payments')
          .filter(bill_type=bill_type))
    qs = apply_date_range(qs, 'bill_date', start, end)

    if q:
        qs = qs.filter(
            Q(bill_number__icontains=q) |
            Q(patient__name__icontains=q) |
            Q(patient__phone_number__icontains=q) |
            Q(patient__file_number__icontains=q)
        )

    if payment_method and payment_method != 'all':
        qs = qs.filter(payments__method=payment_method).distinct()

    if balance_status:
        if balance_status == 'due':
            qs = qs.filter(paid_amount__lt=F('total_amount'))
        elif balance_status == 'advance':
            qs = qs.filter(paid_amount__gt=F('total_amount'))
        elif balance_status == 'settled':
            qs = qs.filter(paid_amount=F('total_amount'))

    qs = qs.annotate(
        raw_balance=F('total_amount') - F('paid_amount'),
        due=Case(
            When(total_amount__gt=F('paid_amount'),
                 then=F('total_amount') - F('paid_amount')),
            default=Value(0),
            output_field=DecimalField(max_digits=10, decimal_places=2)
        ),
        advance=Case(
            When(paid_amount__gt=F('total_amount'),
                 then=F('paid_amount') - F('total_amount')),
            default=Value(0),
            output_field=DecimalField(max_digits=10, decimal_places=2)
        )
    ).order_by('-bill_date')

    selected = {
        'from': start,
        'to': end,
        'q': q,
        'method': payment_method or 'all',
        'balance_status': balance_status or '',
        'range': range_param,
    }
    return qs, selected


@group_required('Receptionist', 'CRO', 'OperationsManager', 'Doctor', 'PharmacyManager', 'Staff')
def service_bill_list(request):
    qs, selected = _bill_queryset_with_filters(request, bill_type='service')
    ctx = {
        'title': 'Service Bills',
        'bills': qs,
        'status_choices': [('all', 'All')] + BILL_STATUS_CHOICES_UI,
        'method_choices': [('all', 'All')] + PAYMENT_METHOD_CHOICES,
        'selected': selected,
        'page_kind': 'service',
        'create_url_name': 'service_bill_create',
    }
    return render(request, 'bills/service_list.html', ctx)

@group_required('Receptionist', 'CRO', 'OperationsManager', 'Doctor', 'PharmacyManager', 'Staff')
def pharmacy_bill_list(request):
    qs, selected = _bill_queryset_with_filters(request, bill_type='pharmacy')
    ctx = {
        'title': 'Pharmacy Bills',
        'bills': qs,
        'status_choices': [('all', 'All')] + BILL_STATUS_CHOICES_UI,
        'method_choices': [('all', 'All')] + PAYMENT_METHOD_CHOICES,
        'selected': selected,
        'page_kind': 'pharmacy',
        'create_url_name': 'pharmacy_sale_create',
    }
    return render(request, 'bills/pharmacy_list.html', ctx)

# ---------- SERVICE BILL ----------

def finalize_bill_totals(bill):
    """Calculate final bill totals including tax and discount"""
    D0 = Decimal('0.00')
    
    # Calculate subtotal from items
    subtotal = bill.items.aggregate(s=Sum('total_price'))['s'] or D0
    
    # Apply tax and discount
    tax = bill.tax_amount or D0
    discount = bill.discount_amount or D0
    final_total = subtotal + tax - discount
    
    # Update bill total (no balance update yet)
    bill.total_amount = final_total
    bill.save(update_fields=['total_amount'])


def update_patient_balance_for_bill(bill, is_new=False):
    """Update patient balance for bill changes"""
    if not bill.patient_id:
        return
    
    D0 = Decimal('0.00')
    current_total = bill.total_amount or D0
    
    if is_new:
        # New bill - add total to patient balance
        if current_total > 0:
            type(bill.patient).objects.filter(pk=bill.patient_id).update(
                balance=F('balance') + current_total
            )
    else:
        # Bill update - we'll handle this in the view by calculating the delta
        pass

@group_required('Receptionist','OperationsManager','Doctor','PharmacyManager')
@transaction.atomic
def service_bill_create(request):
    if request.method == 'POST':
        header_form = BillHeaderForm(request.POST)

        if header_form.is_valid():
            # Create bill without updating patient balance yet
            bill = header_form.save(commit=False)
            bill.bill_type = 'service'
            bill.created_by = request.user
            bill.save()  # Save without balance update

            formset = ServiceBillItemFormSet(request.POST, instance=bill)
            if formset.is_valid():
                # Save non-empty items
                saved_any = False
                for f in formset.forms:
                    if getattr(f, '_empty_row_skip', False) or f.cleaned_data.get('DELETE'):
                        continue
                    it = f.save(commit=False)
                    it.bill = bill
                    it.kind = 'service'
                    it.save()  # This updates bill.total_amount but not patient balance
                    saved_any = True

                if not saved_any:
                    transaction.set_rollback(True)
                    messages.error(request, "Add at least one service item.")
                    return render(request, 'bills/service_bill_create.html', {
                        'header_form': header_form,
                        'formset': ServiceBillItemFormSet(),
                        'is_edit': False,
                    })

                finalize_bill_totals(bill)
                
                # NOW update patient balance for the complete bill
                update_patient_balance_for_bill(bill, is_new=True)

                # Handle payment
                paid = header_form.cleaned_data.get('paid_amount') or Decimal('0.00')
                method = header_form.cleaned_data.get('payment_method')
                bill.paid_amount = paid
                bill.save(update_fields=['paid_amount'])
                
                if paid > 0 and method:
                    Payment.objects.create(
                        patient=bill.patient, 
                        bill=bill, 
                        amount=paid, 
                        method=method,
                        received_by=request.user,
                    )

                messages.success(request, f"Service bill #{bill.bill_number} created successfully.")
                return redirect('bill_receipt', pk=bill.pk)

            # Invalid items
            transaction.set_rollback(True)
            messages.error(request, "Please fix the errors below.")
            return render(request, 'bills/service_bill_create.html', {
                'header_form': header_form,
                'formset': ServiceBillItemFormSet(),
                'is_edit': False,
            })

        # Invalid header
        messages.error(request, "Please fix the errors below.")
        return render(request, 'bills/service_bill_create.html', {
            'header_form': header_form,
            'formset': ServiceBillItemFormSet(),
            'is_edit': False,
        })

    # GET
    return render(request, 'bills/service_bill_create.html', {
        'header_form': BillHeaderForm(),
        'formset': ServiceBillItemFormSet(),
        'is_edit': False,
    })


@group_required('Receptionist','OperationsManager','Doctor','PharmacyManager')
@transaction.atomic
def service_bill_edit(request, pk):
    bill = get_object_or_404(Bill, pk=pk, bill_type='service')
    D0 = Decimal('0.00')

    if request.method == 'POST':
        header_form = BillHeaderForm(request.POST, instance=bill)
        formset = ServiceBillItemFormSet(request.POST, instance=bill)

        if header_form.is_valid() and formset.is_valid():
            old_total = bill.total_amount or D0
            old_paid_total = bill.payments.aggregate(s=Sum('amount'))['s'] or D0

            # Save header (no balance update)
            bill = header_form.save(commit=False)
            if not bill.created_by:
                bill.created_by = request.user
            bill.save()

            # Save items → updates bill.total_amount
            formset.save()

            # Finalize totals
            finalize_bill_totals(bill)

            # Adjust balance for bill total delta
            new_total = bill.total_amount or D0
            total_delta = new_total - old_total
            if total_delta != 0:
                type(bill.patient).objects.filter(pk=bill.patient_id).update(
                    balance=F('balance') + total_delta
                )

            # --- Payment delta handling ---
            new_paid_total = header_form.cleaned_data.get('paid_amount') or D0
            new_method     = header_form.cleaned_data.get('payment_method')

            # 1) Remove old payments *one by one* so Payment.delete() runs
            for p in bill.payments.all():
                p.delete()

            # 2) Persist the bill's paid_amount field
            bill.paid_amount = new_paid_total
            bill.save(update_fields=['paid_amount'])

            # 3) Recreate a single payment that matches the form total & method
            #    (Payment.save() will correctly adjust patient balance)
            if new_paid_total > D0 and new_method:
                Payment.objects.create(
                    patient=bill.patient,
                    bill=bill,
                    amount=new_paid_total,
                    method=new_method,            # <-- this is now always written
                    received_by=request.user,
                )
            # --- end payments ---

            messages.success(request, f"Service bill #{bill.bill_number} updated successfully.")
            return redirect('bill_receipt', pk=bill.pk)

        messages.error(request, "Please fix the errors below.")
    else:
        header_form = BillHeaderForm(instance=bill)
        formset = ServiceBillItemFormSet(instance=bill)

    return render(request, 'bills/service_bill_edit.html', {
        'header_form': header_form,
        'formset': formset,
        'bill': bill,
        'is_edit': True,
    })


@group_required('PharmacyManager','OperationsManager','Receptionist','Doctor')
@transaction.atomic
def pharmacy_bill_create(request):
    if request.method == 'POST':
        header_form = BillHeaderForm(request.POST)
        
        if header_form.is_valid():
            # Create bill without updating patient balance yet
            bill = header_form.save(commit=False)
            bill.bill_type = 'pharmacy'
            bill.created_by = request.user
            bill.save()  # Save without balance update

            formset = PharmacyBillItemFormSet(request.POST, instance=bill)
            if formset.is_valid():
                # Save non-empty items
                saved_any = False
                for f in formset.forms:
                    if getattr(f, '_empty_row_skip', False) or f.cleaned_data.get('DELETE'):
                        continue
                    it = f.save(commit=False)
                    it.bill = bill
                    it.kind = 'pharmacy'
                    it.save()  # This updates bill.total_amount but not patient balance
                    saved_any = True

                if not saved_any:
                    transaction.set_rollback(True)
                    messages.error(request, "Add at least one medicine item.")
                    return render(request, 'bills/pharmacy_bill_create.html', {
                        'header_form': header_form,
                        'formset': PharmacyBillItemFormSet(),
                    })

                # Finalize totals with tax/discount
                finalize_bill_totals(bill)
                
                # NOW update patient balance for the complete bill
                update_patient_balance_for_bill(bill, is_new=True)

                # Handle payment
                paid = header_form.cleaned_data.get('paid_amount') or Decimal('0.00')
                method = header_form.cleaned_data.get('payment_method')
                bill.paid_amount = paid
                bill.save(update_fields=['paid_amount'])
                
                if paid > 0 and method:
                    Payment.objects.create(
                        patient=bill.patient, 
                        bill=bill, 
                        amount=paid, 
                        method=method,
                        received_by=request.user,
                    )

                messages.success(request, f"Pharmacy bill #{bill.bill_number} created successfully.")
                return redirect('bill_receipt', pk=bill.pk)

            transaction.set_rollback(True)
            messages.error(request, "Please fix the errors below.")
            return render(request, 'bills/pharmacy_bill_create.html', {
                'header_form': header_form,
                'formset': PharmacyBillItemFormSet(),
            })
        else:
            messages.error(request, "Please fix the errors below.")
            return render(request, 'bills/pharmacy_bill_create.html', {
                'header_form': header_form,
                'formset': PharmacyBillItemFormSet(),
            })

    # GET
    return render(request, 'bills/pharmacy_bill_create.html', {
        'header_form': BillHeaderForm(),
        'formset': PharmacyBillItemFormSet(),
    })


@group_required('PharmacyManager','OperationsManager','Receptionist','Doctor')
@transaction.atomic
def pharmacy_bill_edit(request, pk):
    bill = get_object_or_404(Bill, pk=pk, bill_type='pharmacy')
    D0 = Decimal('0.00')

    if request.method == 'POST':
        header_form = BillHeaderForm(request.POST, instance=bill)
        formset = PharmacyBillItemFormSet(request.POST, instance=bill)

        if header_form.is_valid() and formset.is_valid():
            old_total = bill.total_amount or D0
            old_paid_total = bill.payments.aggregate(s=Sum('amount'))['s'] or D0

            # Save header (no balance update)
            bill = header_form.save(commit=False)
            if not bill.created_by:
                bill.created_by = request.user
            bill.save()

            # Save items → updates bill.total_amount
            formset.save()

            # Finalize totals
            finalize_bill_totals(bill)

            # Adjust balance for bill total delta
            new_total = bill.total_amount or D0
            total_delta = new_total - old_total
            if total_delta != 0:
                type(bill.patient).objects.filter(pk=bill.patient_id).update(
                    balance=F('balance') + total_delta
                )

            # --- Payment delta handling ---
            new_paid_total = header_form.cleaned_data.get('paid_amount') or D0
            new_method     = header_form.cleaned_data.get('payment_method')

            # 1) Remove old payments *one by one* so Payment.delete() runs
            for p in bill.payments.all():
                p.delete()

            # 2) Persist the bill's paid_amount field
            bill.paid_amount = new_paid_total
            bill.save(update_fields=['paid_amount'])

            # 3) Recreate a single payment that matches the form total & method
            #    (Payment.save() will correctly adjust patient balance)
            if new_paid_total > D0 and new_method:
                Payment.objects.create(
                    patient=bill.patient,
                    bill=bill,
                    amount=new_paid_total,
                    method=new_method,            # <-- this is now always written
                    received_by=request.user,
                )
            # --- end payments ---

            messages.success(request, f"Pharmacy bill #{bill.bill_number} updated successfully.")
            return redirect('bill_receipt', pk=bill.pk)

        messages.error(request, "Please fix the errors below.")
    else:
        header_form = BillHeaderForm(instance=bill)
        formset = PharmacyBillItemFormSet(instance=bill)

    return render(request, 'bills/pharmacy_bill_edit.html', {
        'header_form': header_form,
        'formset': formset,
        'bill': bill,
        'is_edit': True,
    })


@group_required('Receptionist','OperationsManager','Doctor','PharmacyManager')
def bill_receipt(request, pk):
    D0 = Decimal('0.00')

    bill = get_object_or_404(Bill.objects.select_related('patient'), pk=pk)
    items = bill.items.select_related('service', 'medicine').all()

    # Subtotal = sum of line totals
    subtotal = items.aggregate(s=Sum('total_price'))['s'] or D0

    # Payments attached to THIS bill
    payments = bill.payments.order_by('date')
    paid_total = payments.aggregate(s=Sum('amount'))['s'] or D0
    last_payment = payments.last()
    method_display = last_payment.get_method_display() if last_payment else ''

    # Balances
    balance_for_this_bill = (bill.total_amount or D0) - (paid_total or D0)
    patient_balance = bill.patient.balance or D0  # +ve = due, -ve = advance

    # Simple status label
    if balance_for_this_bill <= 0 and (bill.total_amount or D0) > 0:
        bill_status = "Paid in full"
    elif paid_total > 0:
        bill_status = "Partially paid"
    else:
        bill_status = "Unpaid"

    context = {
        'bill': bill,
        'items': items,
        'payments': payments,

        # Numbers for template
        'subtotal': subtotal,
        'paid': paid_total,
        'method_display': method_display,
        'balance_for_this_bill': balance_for_this_bill,
        'patient_balance': patient_balance,
        'bill_status': bill_status,
    }
    return render(request, 'bills/receipt.html', context)

@login_required
@require_GET
def patient_previous_bills(request, patient_id):
    """
    API: Return patient's previous bills (excluding current ongoing bill if needed).
    """
    bills = (
        Bill.objects.filter(patient_id=patient_id)
        .select_related("created_by")
        .order_by("-bill_date")[:10]  # limit to last 10 bills
    )

    data = []
    for b in bills:
        data.append({
            "id": str(b.id),
            "bill_number": b.bill_number,
            "bill_type": b.get_bill_type_display(),
            "bill_date": b.bill_date.strftime("%Y-%m-%d %H:%M"),
            "total_amount": float(b.total_amount or 0),
            "paid_amount": float(b.paid_amount or 0),
            "balance_due": float((b.total_amount or 0) - (b.paid_amount or 0)),
            "created_by": b.created_by.username if b.created_by else None,
        })

    return JsonResponse({"bills": data})

# ---------------- Medicals ----------------
@group_required('PharmacyManager','OperationsManager','Doctor','Receptionist','Staff')
def medicine_list(request):
    # Get all medicines with related category data
    medicines = Medicine.objects.select_related('category').order_by('name')
    
    # Get all categories that have at least one medicine associated for the filter dropdown
    categories = MedicineCategory.objects.filter(medicine__isnull=False).distinct().order_by('name')
    
    # Get medicine type choices for the filter dropdown
    medicine_types = Medicine.MEDICINE_TYPE_CHOICES  # Assuming you have this defined in your model
    
    context = {
        'medicines': medicines,
        'categories': categories,
        'medicine_types': medicine_types,
    }
    
    return render(request, 'pharmacy/medicines_list.html', context)

@group_required('PharmacyManager','OperationsManager','Doctor')
def medicine_create(request):
    if request.method == 'POST':
        form = MedicineForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            messages.success(request, f"Medicine '{obj.name}' added.")
            return redirect('pharmacy_medicine_list')
    else:
        form = MedicineForm()
    return render(request, 'pharmacy/medicines_form.html', {'form': form})

@group_required('PharmacyManager','OperationsManager','Receptionist','Doctor','Staff')
def pharmacy_medicine_detail(request, pk):
    med = get_object_or_404(Medicine, pk=pk)

    # Ensure a stock row exists (optional safety)
    stock, _ = MedicineStock.objects.get_or_create(
        medicine=med, defaults={'current_quantity': 0, 'reserved_quantity': 0}
    )

    recent_txs = (StockTransaction.objects
                  .filter(medicine=med)
                  .order_by('-created_at')[:25])

    low_stock = bool(med.minimum_stock_level and stock.current_quantity < med.minimum_stock_level)

    ctx = {
        'medicine': med,
        'stock': stock,
        'recent_txs': recent_txs,
        'low_stock': low_stock,
    }
    return render(request, 'pharmacy/medicine_detail.html', ctx)

@group_required('PharmacyManager','OperationsManager','Doctor')
def pharmacy_medicine_edit(request, pk):
    med = get_object_or_404(Medicine, pk=pk)
    if request.method == 'POST':
        form = MedicineForm(request.POST, instance=med)
        if form.is_valid():
            form.save()
            messages.success(request, "Medicine updated.")
            return redirect('pharmacy_medicine_detail', pk=med.pk)
        messages.error(request, "Please fix the errors below.")
    else:
        form = MedicineForm(instance=med)

    return render(request, 'pharmacy/medicine_form_edit.html', {
        'form': form,
        'medicine': med,
    })


@group_required('PharmacyManager','OperationsManager','Receptionist','Doctor')
def pharmacy_stock_list(request):
    q = (request.GET.get('q') or '').strip()
    stocks = (MedicineStock.objects
              .select_related('medicine')
              .order_by('medicine__name'))
    if q:
        stocks = stocks.filter(
            Q(medicine__name__icontains=q) |
            Q(medicine__generic_name__icontains=q) |
            Q(medicine__manufacturer__icontains=q)
        )
    return render(request, 'pharmacy/stock_list.html', {'stocks': stocks, 'q': q})


@group_required('PharmacyManager','OperationsManager','Receptionist','Doctor')
@transaction.atomic
def pharmacy_stock_adjust(request, pk):
    stock = get_object_or_404(MedicineStock.objects.select_related('medicine'), medicine_id=pk)

    if request.method == 'POST':
        form = StockAdjustForm(request.POST)
        if form.is_valid():
            new_qty = form.cleaned_data['target_quantity']
            note    = form.cleaned_data['note']
            old_qty = stock.current_quantity
            delta   = new_qty - old_qty

            if delta == 0:
                messages.info(request, "No change in quantity.")
                return redirect('pharmacy_stock_list')

            StockTransaction.objects.create(
                medicine=stock.medicine,
                transaction_type='adjustment',
                quantity=delta,
                unit_price=0,
                batch_number='',
                expiry_date=None,
                supplier='',
                reference_number=f"ADJ-{timezone.now():%Y%m%d%H%M%S}",
                patient=None,
                notes=f"Manual adjustment from {old_qty} to {new_qty}" + (f". {note}" if note else ""),
                created_by=request.user,
            )

            messages.success(
                request,
                f"Adjusted '{stock.medicine.name}' from {old_qty} to {new_qty}."
            )
            return redirect('pharmacy_stock_list')
    else:
        form = StockAdjustForm(initial={'target_quantity': stock.current_quantity})

    return render(request, 'pharmacy/stock_adjust.html', {
        'form': form,
        'stock': stock,
    })

@group_required('PharmacyManager','OperationsManager','Doctor')
def stock_tx_list(request):
    from datetime import date, timedelta
    from django.utils import timezone

    t = (request.GET.get('type') or '').strip()
    range_param = (request.GET.get('range') or '').strip()
    from_str = request.GET.get('from') or request.GET.get('start') or ''
    to_str   = request.GET.get('to')   or request.GET.get('end')   or ''

    today = timezone.localdate()

    def parse_iso(s, default=None):
        try:
            return date.fromisoformat(s) if s else default
        except ValueError:
            return default

    # Resolve start/end from quick range or explicit inputs
    if range_param:
        if range_param == 'today':
            start, end = today, today
        elif range_param == '7d':
            start, end = today - timedelta(days=6), today
        elif range_param == 'month':
            start = today.replace(day=1)
            if today.month == 12:
                end = today.replace(year=today.year+1, month=1, day=1) - timedelta(days=1)
            else:
                end = today.replace(month=today.month+1, day=1) - timedelta(days=1)
        else:
            start, end = parse_iso(from_str, None), parse_iso(to_str, None)
    else:
        start, end = parse_iso(from_str, None), parse_iso(to_str, None)

    # ✅ Default to today if nothing provided
    if not range_param and not from_str and not to_str:
        start = end = today
        range_param = 'today'

    # Normalize inverted dates
    if start and end and end < start:
        start, end = end, start

    qs = (StockTransaction.objects
          .select_related('medicine','patient')
          .order_by('-created_at'))

    # Type filter
    if t in dict(StockTransaction.TRANSACTION_TYPE_CHOICES):
        qs = qs.filter(transaction_type=t)

    # Date filter on created_at (date part)
    qs = apply_date_range(qs, 'created_at', start, end)

    ctx = {
        'txs': qs,
        'type_choices': StockTransaction.TRANSACTION_TYPE_CHOICES,
        'selected_type': t,
        'selected': {
            'from': start,
            'to': end,
            'range': range_param,
            'type': t,
        },
    }
    return render(request, 'pharmacy/transactions_list.html', ctx)


@group_required('PharmacyManager','OperationsManager', 'Doctor')
def stock_tx_create(request):
    if request.method == 'POST':
        form = StockTransactionForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            messages.success(request, f"Transaction recorded for '{obj.medicine.name}'.")
            return redirect('pharmacy_tx_list')
    else:
        form = StockTransactionForm()
    return render(request, 'pharmacy/transactions_form.html', {'form': form})

@group_required('PharmacyManager','OperationsManager','Doctor','Receptionist')
def pharmacy_tx_detail(request, pk):
    tx = get_object_or_404(
        StockTransaction.objects.select_related('medicine','patient','created_by'),
        pk=pk
    )
    return render(request, 'pharmacy/tx_detail.html', {'tx': tx})

@group_required('PharmacyManager','OperationsManager','Doctor')
@transaction.atomic
def pharmacy_tx_edit(request, pk):
    tx = get_object_or_404(StockTransaction, pk=pk)

    if tx.transaction_type in ('sale', 'adjustment'):
        messages.error(request, "Sale and Adjustment transactions cannot be edited.")
        return redirect('pharmacy_tx_detail', pk=tx.pk)
    
    if request.method == 'POST':
        form = StockTransactionForm(request.POST, instance=tx)
        if form.is_valid():
            obj = form.save(commit=False)
            if not obj.created_by:
                obj.created_by = request.user
            obj.save()  # your signals adjust stock
            messages.success(request, "Transaction updated.")
            return redirect('pharmacy_tx_detail', pk=obj.pk)
        messages.error(request, "Please fix the errors below.")
    else:
        form = StockTransactionForm(instance=tx)
    return render(request, 'pharmacy/tx_form_edit.html', {'form': form, 'tx': tx, 'is_edit': True})

# ---------------- Leads ----------------
@group_required('CRO','OperationsManager', 'Doctor')
def lead_list(request):
    q       = request.GET.get('q', '').strip()
    src     = request.GET.get('source', '').strip()
    pri     = request.GET.get('priority', '').strip()
    status  = request.GET.get('status', '').strip()
    from_s  = request.GET.get('from', '').strip()
    to_s    = request.GET.get('to', '').strip()

    # Base queryset
    qs = (Lead.objects
          .select_related('lead_source', 'converted_patient')
          .order_by('-created_at'))

    # Text search
    if q:
        qs = qs.filter(
            Q(name__icontains=q) |
            Q(phone_number__icontains=q) |
            Q(email__icontains=q)
        )

    # Facets
    if src:
        qs = qs.filter(lead_source_id=src)
    if pri:
        qs = qs.filter(priority=pri)
    if status == 'open':
        qs = qs.filter(converted_patient__isnull=True)
    elif status == 'converted':
        qs = qs.filter(converted_patient__isnull=False)

    # --- Date range (Created Date) ---
    # NOTE: If you prefer to filter by next_followup_date instead,
    # change the field passed to apply_date_range below.
    def parse_d(s):
        try:
            return datetime.strptime(s, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return None

    d_from = parse_d(from_s)
    d_to   = parse_d(to_s)

    qs = apply_date_range(qs, 'created_at', d_from, d_to)

    ctx = {
        'leads': qs,
        'sources': LeadSource.objects.filter(is_active=True).order_by('name'),
        'priorities': dict(Lead.PRIORITY_CHOICES),
        'selected': {
            'q': q, 'source': src, 'priority': pri, 'status': status,
            'from': d_from, 'to': d_to,
        },
    }
    return render(request, 'leads/list.html', ctx)

@group_required('CRO','OperationsManager', 'Doctor')
def lead_create(request):
    if request.method == 'POST':
        form = LeadForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            messages.success(request, "Lead created.")
            return redirect('lead_detail', pk=obj.pk)
    else:
        form = LeadForm()
    return render(request, 'leads/form.html', {'form': form})

@group_required('CRO','OperationsManager', 'Doctor')
def lead_update(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    if request.method == 'POST':
        form = LeadForm(request.POST, instance=lead)
        if form.is_valid():
            form.save()
            messages.success(request, "Lead updated.")
            return redirect('lead_detail', pk=lead.pk)
    else:
        form = LeadForm(instance=lead)
    return render(request, 'leads/form.html', {'form': form})

@group_required('CRO','OperationsManager','Doctor')
def lead_detail(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    return render(request, 'leads/detail.html', {'lead': lead})

@group_required('CRO','OperationsManager','Doctor')
def lead_convert(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    if lead.converted_patient_id:
        messages.info(request, "This lead is already converted to a patient.")
        return redirect('lead_detail', pk=lead.pk)

    if request.method == 'POST':
        form = LeadConvertForm(request.POST)
        if form.is_valid():
            patient = form.save(commit=False)
            patient.registered_by = request.user
            patient.save()
            lead.converted_patient = patient
            lead.conversion_date = timezone.now()
            lead.save(update_fields=['converted_patient','conversion_date'])
            messages.success(request, f"Lead converted: {patient.name} ({patient.file_number}).")
            return redirect('lead_detail', pk=lead.pk)
    else:
        initial = {
            'name': lead.name,
            'age': lead.age or '',
            'phone_number': lead.phone_number,
            'email': lead.email or '',
            'address': lead.location or '',
            'city': '', 'state': '', 'pincode': '', 'occupation': ''
        }
        form = LeadConvertForm(initial=initial)
    return render(request, 'leads/convert.html', {'form': form, 'lead': lead})

# ---------------- Expenses ----------------
@group_required('OperationsManager','Doctor','ConsultingDoctor')
def expense_list(request):
    status = (request.GET.get('status') or '').strip()
    range_param = (request.GET.get('range') or '').strip()
    pending_all = request.GET.get('pending_all') == '1'   # <<< NEW

    today = timezone.localdate()
    start_str = request.GET.get('from') or request.GET.get('start') or request.GET.get('date')
    end_str   = request.GET.get('to')   or request.GET.get('end')

    def parse_iso(d, default=None):
        try:
            return date.fromisoformat(d) if d else default
        except ValueError:
            return default

    # If "All Pending" is requested, drop date constraints entirely
    if pending_all and status == 'pending':
        start = None
        end = None
    else:
        # Compute start/end from quick range if provided
        if range_param:
            if range_param == 'today':
                start = today
                end = today
            elif range_param == '7d':
                start = today - timedelta(days=6)
                end = today
            elif range_param == 'month':
                start = today.replace(day=1)
                if today.month == 12:
                    end = today.replace(year=today.year+1, month=1, day=1) - timedelta(days=1)
                else:
                    end = today.replace(month=today.month+1, day=1) - timedelta(days=1)
            else:
                start = parse_iso(start_str, today)
                end   = parse_iso(end_str, None)
        else:
            start = parse_iso(start_str, today)
            end   = parse_iso(end_str, None)

    qs = (Expense.objects
          .select_related('category','requested_by','approved_by')
          .order_by('-expense_date'))

    # Date filtering (skip if pending_all=true)
    if not (pending_all and status == 'pending'):
      if start:
          qs = qs.filter(expense_date__gte=start)
      if end:
          if start and end < start:
              start, end = end, start
              qs = qs.filter(expense_date__gte=start)
          qs = qs.filter(expense_date__lte=end)

    # Status filter (support 'all')
    if status and status != 'all' and status in dict(Expense.STATUS_CHOICES):
        qs = qs.filter(status=status)

    can_mark_paid = request.user.groups.filter(name__in=["OperationsManager", "Doctor"]).exists()

    total_amount = qs.aggregate(
        total=Coalesce(Sum('amount'), Decimal('0.00'))
    )['total']

    ctx = {
        'expenses': qs,
        'status_choices': Expense.STATUS_CHOICES,
        'status_choicesfilter': [('all','All')] + list(Expense.STATUS_CHOICES),
        'selected_status': status or 'all',
        'can_mark_paid': can_mark_paid,
        'selected': {
            'from': start,
            'to': end,
            'status': status or 'all',
            'range': range_param,
        },
        'total_amount': total_amount,
    }
    return render(request, 'expenses/list.html', ctx)


@login_required
def my_expense_list(request):
    """
    List only the expenses created/requested by the current user.
    Same UX as expense_list: quick ranges, manual dates, status, 'All Pending', total.
    """
    status      = (request.GET.get('status') or '').strip()
    range_param = (request.GET.get('range') or '').strip()
    pending_all = request.GET.get('pending_all') == '1'

    today    = timezone.localdate()
    start_str = request.GET.get('from') or request.GET.get('start') or request.GET.get('date')
    end_str   = request.GET.get('to')   or request.GET.get('end')

    def parse_iso(d, default=None):
        try:
            return date.fromisoformat(d) if d else default
        except ValueError:
            return default

    # Date window
    if pending_all and status == 'pending':
        start = None
        end   = None
    else:
        if range_param:
            if range_param == 'today':
                start = today
                end   = today
            elif range_param == '7d':
                start = today - timedelta(days=6)
                end   = today
            elif range_param == 'month':
                start = today.replace(day=1)
                if today.month == 12:
                    end = today.replace(year=today.year+1, month=1, day=1) - timedelta(days=1)
                else:
                    end = today.replace(month=today.month+1, day=1) - timedelta(days=1)
            else:
                start = parse_iso(start_str, today)
                end   = parse_iso(end_str, None)
        else:
            start = parse_iso(start_str, today)
            end   = parse_iso(end_str, None)

    qs = (
        Expense.objects
        .select_related('category','requested_by','approved_by')
        .filter(requested_by=request.user)           # <<< ONLY my expenses
        .order_by('-expense_date')
    )

    # Date filters (skip when "All Pending")
    if not (pending_all and status == 'pending'):
        if start:
            qs = qs.filter(expense_date__gte=start)
        if end:
            if start and end < start:
                start, end = end, start
                qs = qs.filter(expense_date__gte=start)
            qs = qs.filter(expense_date__lte=end)

    # Status filter
    if status and status != 'all' and status in dict(Expense.STATUS_CHOICES):
        qs = qs.filter(status=status)

    total_amount = qs.aggregate(total=Coalesce(Sum('amount'), Decimal('0.00')))['total']

    ctx = {
        'expenses': qs,
        'status_choices': Expense.STATUS_CHOICES,
        'status_choicesfilter': [('all','All')] + list(Expense.STATUS_CHOICES),
        'selected_status': status or 'all',
        'selected': {
            'from': start,
            'to': end,
            'status': status or 'all',
            'range': range_param,
        },
        'total_amount': total_amount,
        'is_my_expenses': True,   # for template title/labels
    }
    return render(request, 'expenses/my_list.html', ctx)

def expense_create(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            # your model uses requested_by (not created_by)
            obj.requested_by = request.user
            # default status on create if you want (often 'pending')
            if not user_can_edit_status(request.user):
                # enforce default status for non-privileged on create
                obj.status = obj.status or 'pending'
            obj.save()
            messages.success(request, "Expense submitted.")
            return redirect('expense_detail', pk=obj.pk)
    else:
        form = ExpenseForm(user=request.user)
    return render(request, 'expenses/form.html', {'form': form, 'is_edit': False, 'can_edit_status': user_can_edit_status(request.user)})


def expense_update(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES, instance=expense, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Expense updated.")
            return redirect('expense_detail', pk=expense.pk)
    else:
        form = ExpenseForm(instance=expense, user=request.user)
    return render(
        request,
        'expenses/form.html',
        {'form': form, 'is_edit': True, 'expense': expense, 'can_edit_status': user_can_edit_status(request.user)}
    )




#Create



def expense_detail(request, pk):
    expense = get_object_or_404(Expense.objects.select_related('category','requested_by'), pk=pk)
    return render(request, 'expenses/detail.html', {'expense': expense})


@group_required('OperationsManager','Doctor')
def expense_approve(request, pk):
    if request.method != 'POST':
        return redirect('expense_list')
    exp = get_object_or_404(Expense, pk=pk)
    exp.status = 'approved'
    exp.approval_date = timezone.now()
    exp.approved_by = request.user
    exp.save(update_fields=['status','approval_date','approved_by'])
    messages.success(request, "Expense approved.")
    return redirect('expense_list')

@group_required('OperationsManager','Doctor')
def expense_reject(request, pk):
    if request.method != 'POST':
        return redirect('expense_list')
    exp = get_object_or_404(Expense, pk=pk)
    exp.status = 'rejected'
    exp.approval_date = timezone.now()
    exp.approved_by = request.user
    exp.save(update_fields=['status','approval_date','approved_by'])
    messages.info(request, "Expense rejected.")
    return redirect('expense_list')

@group_required('OperationsManager','Doctor')
@require_POST
def expense_mark_paid(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if expense.status != 'approved':
        messages.error(request, "Only approved expenses can be marked as paid.")
        return redirect('expense_detail', pk=pk)
    expense.status = 'paid'
    expense.approved_by = expense.approved_by or request.user
    expense.save(update_fields=['status','approved_by'])
    messages.success(request, "Expense marked as paid.")
    return redirect('expense_detail', pk=pk)


#staffs

@group_required('OperationsManager', 'Doctor')
def staff_list(request):
    q = (request.GET.get('q') or '').strip()
    role = (request.GET.get('role') or '').strip()

    qs = (User.objects
        .filter(is_superuser=False)
        .exclude(id=request.user.id) # <-- Add this line
        .select_related('profile')
        .order_by('first_name', 'last_name', 'username'))

    if role:
        qs = qs.filter(user_type=role)

    if q:
        qs = qs.filter(
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(username__icontains=q) |
            Q(email__icontains=q)
        )

    return render(request, 'staff/list.html', {
        'staff': qs,
        'roles': STAFFABLE_USER_TYPES,
        'selected': {'q': q, 'role': role},
    })

@group_required('OperationsManager', 'Doctor')
def staff_create(request):
    if request.method == 'POST':
        form = StaffCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            _sync_user_role_group(user)  # 👈 enforce correct group
            messages.success(request, f"Staff '{user.get_full_name() or user.username}' created.")
            return redirect('staff_list')
        messages.error(request, "Please fix the errors below.")
    else:
        form = StaffCreateForm(initial={'is_active': True, 'user_type': 'staff'})

    return render(request, 'staff/form.html', {
        'form': form,
        'is_edit': False,
        'title': 'Add Staff',
    })


@group_required('OperationsManager', 'Doctor')
def staff_edit(request, pk):
    user = get_object_or_404(User, pk=pk, is_superuser=False)
    if request.method == 'POST':
        form = StaffEditForm(request.POST, instance=user)
        if form.is_valid():
            user = form.save()
            _sync_user_role_group(user)  # 👈 re-sync group if role changed
            messages.success(request, f"Staff '{user.get_full_name() or user.username}' updated.")
            return redirect('staff_list')
        messages.error(request, "Please fix the errors below.")
    else:
        form = StaffEditForm(instance=user)

    return render(request, 'staff/form.html', {
        'form': form,
        'is_edit': True,
        'title': 'Edit Staff',
        'obj': user,
    })


# ---------- FINANCE REPORT ----------
from django import forms
from django.db.models.functions import Coalesce

class FinanceFilterForm(forms.Form):
    start = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    end = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))

@group_required('OperationsManager','Doctor')
def finance_report(request):
    today = timezone.localdate()
    initial_start = request.GET.get('start', today)
    initial_end = request.GET.get('end', today)

    form = FinanceFilterForm({'start': initial_start, 'end': initial_end})
    ctx = {'form': form, 'summary': {}, 'by_area': []}

    if form.is_valid():
        start = form.cleaned_data['start']
        end = form.cleaned_data['end']

        # ---------------- Bills / Collections / Expenses ----------------
        bills = (
            Bill.objects
            .select_related('patient')
        )
        bills = apply_date_range(bills, 'bill_date', start, end)

        total_collection = bills.aggregate(
            s=Coalesce(Sum('paid_amount'), Decimal('0.00'))
        )['s']

        expenses = Expense.objects.filter(
            expense_date__gte=start,
            expense_date__lte=end,
            status='paid'
        )
        total_expenses = expenses.aggregate(
            s=Coalesce(Sum('amount'), Decimal('0.00'))
        )['s']

        total_billed = bills.aggregate(
            s=Coalesce(Sum('total_amount'), Decimal('0.00'))
        )['s']

        # Pharmacy sales
        pharm_items = (
            BillItem.objects
            .filter(bill__in=bills, kind='pharmacy')
            .select_related('bill', 'medicine')
        )
        total_medicine_sale = pharm_items.aggregate(
            s=Coalesce(Sum('total_price'), Decimal('0.00'))
        )['s']

        # Service sales
        service_items = BillItem.objects.filter(bill__in=bills, kind='service')
        total_service_sale = service_items.aggregate(
            s=Coalesce(Sum('total_price'), Decimal('0.00'))
        )['s']

        # By area (district)
        by_area_qs = (
            pharm_items
            .values('bill__patient__district')
            .annotate(
                qty=Coalesce(Sum('quantity'), 0),
                sale=Coalesce(Sum('total_price'), Decimal('0.00')),
            )
            .order_by('-sale')
        )

        # ---------------- Leads KPIs ----------------
        # NOTE: if your Lead model uses a different created field,
        # change created_at -> created / created_on etc.
        leads_qs = Lead.objects.all()
        leads_qs = apply_date_range(leads_qs, 'created_at', start, end)

        total_leads = leads_qs.count()
        leads_converted = leads_qs.filter(converted_patient__isnull=False).count()
        leads_open = leads_qs.filter(converted_patient__isnull=True).count()
        lead_conversion_rate = (Decimal(leads_converted) / total_leads * Decimal('100.0')) if total_leads else Decimal('0.00')

        ctx['by_area'] = list(by_area_qs)
        ctx['summary'] = {
            'period': f"{start.strftime('%d-%b-%Y')} to {end.strftime('%d-%b-%Y')}",
            'area': 'All',

            'total_billed': total_billed,
            'total_collection': total_collection,
            'total_expenses': total_expenses,
            'net': total_collection - total_expenses,
            'total_medicine_sale': total_medicine_sale,
            'total_service_sale': total_service_sale,

            # Leads
            'total_leads': total_leads,
            'leads_converted': leads_converted,
            'leads_open': leads_open,
            'lead_conversion_rate': lead_conversion_rate,  # percent
        }


    return render(request, 'reports/finance.html', ctx)

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group


User = get_user_model()

ROLE_GROUPS = ['Doctor', 'ConsultingDoctor', 'OperationsManager', 'PharmacyManager', 'Receptionist', 'Staff', 'CRO', 'SuperUser']
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

def _sync_user_role_group(user):
    to_remove = Group.objects.filter(name__in=ROLE_GROUPS)
    if to_remove.exists():
        user.groups.remove(*to_remove)
    gname = ROLE_GROUP_MAP.get(user.user_type)
    if gname:
        g, _ = Group.objects.get_or_create(name=gname)
        user.groups.add(g)

