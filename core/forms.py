
from django import forms
from .models import *
from django.utils import timezone
from datetime import datetime, time, timedelta
from .models import Appointment, Branch
from django.db.models import Sum, F
from django.db.models.functions import Coalesce
from django.forms import BaseInlineFormSet, inlineformset_factory

DEFAULT_APPT_TIME = time(hour=10, minute=0)

class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = [
            'name','age','date_of_birth','gender','phone_number','email',
            'address','city','district','pincode','occupation','referred_by','referral_source'
        ]
        widgets = {
            'date_of_birth': forms.TextInput(attrs={
                'class': 'form-control datepicker',   # hook for JS
                'placeholder': 'DD-MM-YYYY',
                'autocomplete': 'off'
            }),
            'email': forms.EmailInput(attrs={'placeholder': 'name@example.com'}),
            'phone_number': forms.TextInput(attrs={'type': 'tel', 'placeholder': '+91XXXXXXXXXX'}),
            'address': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if dob and dob > timezone.localdate():
            raise forms.ValidationError("Date of birth cannot be in the future.")
        return dob

    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Bootstrap classes to all widgets
        for field in self.fields.values():
            w = field.widget
            if isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs['class'] = (w.attrs.get('class', '') + ' form-select').strip()
            elif isinstance(w, forms.CheckboxInput):
                w.attrs['class'] = (w.attrs.get('class', '') + ' form-check-input').strip()
            else:
                w.attrs['class'] = (w.attrs.get('class', '') + ' form-control').strip()

                
class AppointmentBaseForm(forms.ModelForm):
    appointment_date = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={
                "type": "datetime-local",
                "placeholder": "Select date & time",
                "class": "form-control datepicker",
            },
            format="%Y-%m-%dT%H:%M",
        ),
        input_formats=["%Y-%m-%dT%H:%M"],
        help_text="Select the appointment date & time",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Patient / Doctor dropdowns — only if those fields are present
        if 'patient' in self.fields:
            self.fields['patient'].queryset = Patient.objects.filter(is_active=True).order_by('name')
            self.fields['patient'].label_from_instance = (
                lambda p: f"{p.name} ({p.file_number})" if p.file_number else p.name
            )

        if 'assigned_doctor' in self.fields:
            self.fields['assigned_doctor'].queryset = (
                User.objects.filter(is_active=True, user_type__in=['doctor', 'consulting_doctor'])
                    .order_by('first_name','last_name','username')
            )
            self.fields['assigned_doctor'].label_from_instance = lambda u: f"Dr {u.get_full_name() or u.username}"


        if 'branch' in self.fields:
            self.fields['branch'].queryset = Branch.objects.filter(is_active=True).order_by('name')
            self.fields['branch'].label_from_instance = lambda b: b.name
            self.fields['branch'].required = True
            self.fields['branch'].empty_label = 'Select branch'

        # min datetime = now (local) — only if the field exists
        if 'appointment_date' in self.fields:
            self.fields['appointment_date'].widget.attrs.setdefault(
                "min", timezone.localtime().strftime("%Y-%m-%dT%H:%M")
            )

            # CRITICAL FIX: Set initial value in LOCAL timezone to match what user sees
            if self.instance and self.instance.pk and self.instance.appointment_date:
                # Convert to local timezone and normalize to minute precision
                local_dt = timezone.localtime(self.instance.appointment_date)
                local_dt = local_dt.replace(second=0, microsecond=0)
                self.initial['appointment_date'] = local_dt

        # bootstrap classes
        for f in self.fields.values():
            w = f.widget
            if w.__class__.__name__ in ('Select','SelectMultiple'):
                w.attrs['class'] = (w.attrs.get('class','') + ' form-select').strip()
            elif getattr(w, 'input_type', '') not in ('checkbox','radio','submit'):
                w.attrs['class'] = (w.attrs.get('class','') + ' form-control').strip()

    def clean_appointment_date(self):
        dt = self.cleaned_data.get("appointment_date")
        if dt is None:
            return dt
            
        print(f"DEBUG FORM: Received datetime from form: {dt} (naive: {timezone.is_naive(dt)})")
        
        # The datetime-local input gives us a naive datetime in the user's local timezone
        if timezone.is_naive(dt):
            # Convert the naive datetime to aware datetime in the current timezone
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
            print(f"DEBUG FORM: Converted to aware: {dt}")
        
        # normalize to minute precision
        dt = dt.replace(second=0, microsecond=0)
        
        # Check against current time in local timezone
        now_local = timezone.localtime().replace(second=0, microsecond=0)
        if dt < now_local:
            raise forms.ValidationError("Appointment date/time cannot be in the past.")
            
        print(f"DEBUG FORM: Final cleaned datetime: {dt}")
        return dt


class AppointmentCreateForm(AppointmentBaseForm):
    class Meta:
        model = Appointment
        fields = ['patient', 'branch', 'sittings', 'appointment_date', 'assigned_doctor', 'notes']


class AppointmentEditForm(AppointmentBaseForm):
    class Meta:
        model = Appointment
        fields = ['patient', 'branch', 'sittings', 'appointment_date', 'assigned_doctor', 'notes', 'status']
        widgets = {'status': forms.Select(attrs={'class': 'form-select'})}


class AppointmentRescheduleForm(AppointmentBaseForm):
    reschedule_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'Reason (optional)'}),
        label='Reason'
    )

    class Meta:
        model = Appointment
        fields = ['appointment_date', 'assigned_doctor', 'notes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        appt_date = self.initial.get('appointment_date')
        if appt_date:
            if timezone.is_naive(appt_date):
                appt_date = timezone.make_aware(appt_date, timezone.get_current_timezone())
            appt_date = appt_date.replace(second=0, microsecond=0)
            self.initial['appointment_date'] = appt_date



# -------------------------------
# Billing (Service-based)
# -------------------------------
from django.forms import inlineformset_factory

from decimal import Decimal
from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from django.forms.utils import ErrorDict
from .models import Bill, BillItem, Payment
from django.db.models import Sum, Q

class BaseSkipEmptyRowInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        for form in self.forms:
            cleaned = getattr(form, 'cleaned_data', None)
            svc_or_med = None
            qty = None
            price = None

            if cleaned:
                svc_or_med = cleaned.get('service') or cleaned.get('medicine')
                qty = cleaned.get('quantity') or 0
                price = cleaned.get('unit_price')

            is_empty_row = (not svc_or_med) and (qty in (None, 0)) and (price in (None, Decimal('0.00'), 0))
            if is_empty_row:
                form._empty_row_skip = True
                form.cleaned_data = {}
                form._errors = ErrorDict()


class BillHeaderForm(forms.ModelForm):
    paid_amount = forms.DecimalField(
        required=False,
        min_value=0,
        initial=Decimal("0.00"),
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    payment_method = forms.ChoiceField(
        choices=Payment.PAYMENT_METHOD_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Bill
        fields = ['patient', 'remark', 'paid_amount', 'payment_method','tax_amount','discount_amount']
        widgets = {
            'tax_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'discount_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'patient': forms.Select(attrs={'class': 'form-select patient-select'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Any notes…'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['payment_method'].initial = 'cash'

        if self.instance.pk:
            # Get total paid amount for this bill and the last payment method
            total_paid = self.instance.payments.aggregate(total=Sum('amount'))['total'] or Decimal("0.00")
            last_payment = self.instance.payments.last()
            
            self.fields['paid_amount'].initial = total_paid
            if last_payment:
                self.fields['payment_method'].initial = last_payment.method

    def clean(self):
        cleaned = super().clean()
        paid = cleaned.get('paid_amount') or Decimal("0.00")
        method = cleaned.get('payment_method')
        if paid > 0 and not method:
            self.add_error('payment_method', "Select a payment method when an amount is paid.")
        cleaned['paid_amount'] = paid
        return cleaned


class ServiceBillItemForm(forms.ModelForm):
    class Meta:
        model = BillItem
        fields = ['service', 'quantity', 'unit_price']
        widgets = {
            'service': forms.Select(attrs={'class': 'form-select service-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'style': 'width:90px;text-align:center;'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'style': 'width:110px;text-align:right;'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.kind = 'service'
        self.fields['unit_price'].required = False

    def clean(self):
        cleaned = super().clean()
        svc = cleaned.get('service')
        qty = cleaned.get('quantity') or 0
        price = cleaned.get('unit_price')

        is_empty = (not svc) and qty == 0 and (price in (None, Decimal('0.00')))
        if is_empty:
            self._empty_row_skip = True
            return cleaned

        if not svc:
            self.add_error('service', "Select a service.")
        if qty <= 0:
            self.add_error('quantity', "Quantity must be greater than 0.")
        if svc and (price is None or price == 0):
            cleaned['unit_price'] = svc.default_price or Decimal('0.00')

        return cleaned


class PharmacyBillItemForm(forms.ModelForm):
    class Meta:
        model = BillItem
        fields = ['medicine', 'quantity', 'unit_price']
        widgets = {
            'medicine': forms.Select(attrs={'class': 'form-select medicine-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'style': 'width:90px;text-align:center;'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'style': 'width:110px;text-align:right;'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.kind = 'pharmacy'
        self.fields['unit_price'].required = False
        
        # Annotate stock quantity onto the queryset
        medicines = (Medicine.objects
                     .select_related('stock')
                     .annotate(quantity_in_stock=Coalesce(F('stock__current_quantity'), 0))
                     .filter(is_active=True)
                     .order_by('name'))
        self.fields['medicine'].queryset = medicines

    def clean(self):
        cleaned = super().clean()
        med = cleaned.get('medicine')
        qty = cleaned.get('quantity') or 0
        price = cleaned.get('unit_price')

        is_empty = (not med) and qty == 0 and (price in (None, Decimal('0.00')))
        if is_empty:
            self._empty_row_skip = True
            return cleaned

        if not med:
            self.add_error('medicine', "Select a medicine.")
        if qty <= 0:
            self.add_error('quantity', "Quantity must be greater than 0.")
        if med and (price is None or price == 0):
            cleaned['unit_price'] = med.selling_price or Decimal('0.00')
            
        # Stock check
        if med and qty > 0:
            # The annotation gives us this attribute for free
            available_stock = getattr(med, 'quantity_in_stock', 0)
            if qty > available_stock:
                self.add_error('quantity', f"Only {available_stock} in stock.")

        return cleaned


ServiceBillItemFormSet = inlineformset_factory(
    Bill,
    BillItem,
    form=ServiceBillItemForm,
    formset=BaseSkipEmptyRowInlineFormSet,
    fields=['service', 'quantity', 'unit_price'],
    extra=3,
    can_delete=True
)

PharmacyBillItemFormSet = inlineformset_factory(
    Bill,
    BillItem,
    form=PharmacyBillItemForm,
    formset=BaseSkipEmptyRowInlineFormSet,
    fields=['medicine', 'quantity', 'unit_price'],
    extra=3,
    can_delete=True
)


#medicine

class MedicineForm(forms.ModelForm):
    class Meta:
        model = Medicine
        fields = ['name','generic_name','category','medicine_type','strength',
                  'manufacturer','purchase_price','selling_price',
                  'minimum_stock_level','unit_of_measurement','description',
                  'side_effects','contraindications','storage_instructions','is_active']

class StockTransactionForm(forms.ModelForm):
    class Meta:
        model = StockTransaction
        fields = ['medicine','transaction_type','quantity','unit_price',
                  'batch_number','expiry_date','supplier',
                  'reference_number','patient','notes']
        widgets = {
            'expiry_date': forms.DateInput(attrs={'type':'date'})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Exclude 'sale' from the transaction_type choices
        self.fields['transaction_type'].choices = [
            (key, value) for key, value in StockTransaction.TRANSACTION_TYPE_CHOICES
            if key not in ('sale', 'adjustment')
        ]

class StockAdjustForm(forms.Form):
    target_quantity = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
        label='New available quantity'
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        label='Reason (optional)'
    )

class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = [
            'name','phone_number','email','age','location',
            'lead_source','priority',
            'last_contact_date','next_followup_date','notes'
        ]
        widgets = {
            'last_contact_date': forms.DateInput(attrs={'type':'date'}),
            'next_followup_date': forms.DateInput(attrs={'type':'date'}),
        }

class LeadConvertForm(forms.ModelForm):
    """Collect required Patient fields when converting a Lead."""
    class Meta:
        model = Patient
        fields = [
            'name','age','date_of_birth','gender','phone_number','email',
            'address','city','district','pincode','occupation'
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type':'date'}),
        }

class PatientMedicalHistoryForm(forms.ModelForm):
    class Meta:
        model = PatientMedicalHistory
        fields = [
            'hypertension','hypertension_family','diabetes','diabetes_family',
            'thyroid_disorder','thyroid_disorder_family','autoimmune_disease',
            'autoimmune_disease_family','allergies','allergies_family',
            'allergy_details','current_medications','surgical_history','other_conditions'
        ]
        widgets = {
            'allergy_details':     forms.Textarea(attrs={'rows': 2, 'placeholder': 'E.g., drug / food allergies'}),
            'current_medications': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Name, dose, frequency'}),
            'surgical_history':    forms.Textarea(attrs={'rows': 2, 'placeholder': 'Past surgeries / dates'}),
            'other_conditions':    forms.Textarea(attrs={'rows': 2, 'placeholder': 'Anything else important'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Bootstrap classes to all widgets
        for field in self.fields.values():
            w = field.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs['class'] = (w.attrs.get('class', '') + ' form-check-input').strip()
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs['class'] = (w.attrs.get('class', '') + ' form-select').strip()
            else:
                w.attrs['class'] = (w.attrs.get('class', '') + ' form-control').strip()


class HairConsultationForm(forms.ModelForm):
    class Meta:
        model = HairConsultation
        fields = [
            'doctor',
            'hair_loss_onset','hair_loss_duration','affected_area','associated_symptoms',
            'previous_treatments','scalp_condition','hair_density','miniaturization_grade',
            'pull_test','dermoscopy_findings','scalp_zones_image','hair_patterns_image','examination_remarks'
        ]
        widgets = {
            'previous_treatments':   forms.Textarea(attrs={'rows':2}),
            'affected_area':         forms.Textarea(attrs={'rows':2}),
            'associated_symptoms':   forms.Textarea(attrs={'rows':2}),
            'dermoscopy_findings':   forms.Textarea(attrs={'rows':2}),
            'examination_remarks':   forms.Textarea(attrs={'rows':2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # restrict doctor field
        self.fields['doctor'].queryset = (
            User.objects.filter(
                is_active=True,
                user_type__in=['doctor', 'consulting_doctor']
            ).order_by('first_name','last_name','username')
        )
        self.fields['doctor'].label_from_instance = lambda u: (u.get_full_name() or u.username)


        # add bootstrap classes
        for f in self.fields.values():
            w = f.widget
            if isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs['class'] = (w.attrs.get('class','') + ' form-select').strip()
            elif isinstance(w, forms.ClearableFileInput):
                w.attrs['class'] = (w.attrs.get('class','') + ' form-control').strip()
            else:
                w.attrs['class'] = (w.attrs.get('class','') + ' form-control').strip()


class ConsultationPhotoForm(forms.ModelForm):
    class Meta:
        model = ConsultationPhoto
        fields = ['photo_type', 'image', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows':2})}

    def __init__(self, *args, **kwargs):
        self.consultation = kwargs.pop('consultation', None)
        super().__init__(*args, **kwargs)
        # Bootstrap
        self.fields['photo_type'].widget.attrs['class'] = 'form-select'
        self.fields['image'].widget.attrs['class'] = 'form-control'
        self.fields['notes'].widget.attrs['class'] = 'form-control'
        # Limit choices (unique_together)
        if self.consultation:
            used = set(self.consultation.photos.values_list('photo_type', flat=True))
            self.fields['photo_type'].choices = [
                (k, v) for k, v in ConsultationPhoto.PHOTO_TYPE_CHOICES if k not in used
            ]

class TreatmentPlanForm(forms.ModelForm):
    class Meta:
        model = TreatmentPlan
        fields = [
            'primary_diagnosis','differential_factors','procedure',
            'session_frequency','total_sessions','adjunctive_treatments',
            'expected_outcomes_explained','consent_obtained',
            'cost_per_session'
        ]
        widgets = {
            'primary_diagnosis':     forms.Textarea(attrs={'rows': 2, 'placeholder': 'Primary diagnosis'}),
            'differential_factors':  forms.Textarea(attrs={'rows': 2, 'placeholder': 'Differentials / factors'}),
            'adjunctive_treatments': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Topicals / oral meds'}),
            'session_frequency':     forms.TextInput(attrs={'placeholder': 'e.g., every 4 weeks'}),
            'total_sessions':        forms.NumberInput(attrs={'min': 1}),
            'cost_per_session':      forms.NumberInput(attrs={'step': '0.01', 'min': 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Ensure procedure shows only Service.name
        if 'procedure' in self.fields:
            self.fields['procedure'].queryset = Service.objects.filter(is_active=True).order_by("name")
            self.fields['procedure'].label_from_instance = lambda obj: obj.name

        # Bootstrap classes
        for f in self.fields.values():
            w = f.widget
            if isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs['class'] = (w.attrs.get('class','') + ' form-select').strip()
            elif isinstance(w, (forms.CheckboxInput,)):
                w.attrs['class'] = (w.attrs.get('class','') + ' form-check-input').strip()
            elif isinstance(w, (forms.ClearableFileInput,)):
                w.attrs['class'] = (w.attrs.get('class','') + ' form-control').strip()
            else:
                w.attrs['class'] = (w.attrs.get('class','') + ' form-control').strip()


class FollowUpForm(forms.ModelForm):
    # date-only inputs (typing + picker)
    followup_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control datepicker'})
    )
    next_followup_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control datepicker', 'placeholder': 'DD-MM-YYYY'})
    )

    class Meta:
        model = FollowUp
        fields = [
            'followup_date','overall_response_percentage','patient_satisfaction',
            'future_recommendations','maintenance_plan','doctor_remarks','next_followup_date'
        ]
        widgets = {
            'future_recommendations': forms.Textarea(attrs={'rows':2}),
            'maintenance_plan': forms.Textarea(attrs={'rows':2}),
            'doctor_remarks': forms.Textarea(attrs={'rows':2}),
            'overall_response_percentage': forms.TextInput(attrs={
                'class':'form-control','inputmode':'numeric','placeholder':'0–100'
            }),
            'patient_satisfaction': forms.TextInput(attrs={
                'class':'form-control','inputmode':'numeric','placeholder':'1–10'
            }),
        }
    
    def clean_overall_response_percentage(self):
        v = self.cleaned_data.get('overall_response_percentage')
        try:
            v = int(str(v).strip())
        except (TypeError, ValueError):
            raise forms.ValidationError("Enter a number from 0 to 100.")
        if not 0 <= v <= 100:
            raise forms.ValidationError("Must be between 0 and 100.")
        return v

    def clean_patient_satisfaction(self):
        v = self.cleaned_data.get('patient_satisfaction')
        try:
            v = int(str(v).strip())
        except (TypeError, ValueError):
            raise forms.ValidationError("Enter a number from 1 to 10.")
        if not 1 <= v <= 10:
            raise forms.ValidationError("Must be between 1 and 10.")
        return v

class ProgressPhotoForm(forms.ModelForm):
    class Meta:
        model = ProgressPhoto
        fields = ['image','photo_type','notes']
        widgets = {'notes': forms.Textarea(attrs={'rows':2})}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['photo_type'].widget.attrs['class']='form-select'
        self.fields['image'].widget.attrs['class']='form-control'
        self.fields['notes'].widget.attrs['class']='form-control'

ALLOWED_STATUS_EDIT_GROUPS = {'OperationsManager', 'Doctor'}

def user_can_edit_status(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=ALLOWED_STATUS_EDIT_GROUPS).exists()

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['expense_date', 'category', 'amount', 'description', 'attachment', 'status']
        widgets = {
            'expense_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'category':     forms.Select(attrs={'class': 'form-select'}),
            'amount':       forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'description':  forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'attachment':   forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'status':       forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep a flag we can reuse in clean_status()
        self._can_edit_status = user_can_edit_status(user)

        # For non-privileged users, hide status (keep its value) and prevent changes
        if not self._can_edit_status:
            self.fields['status'].widget = forms.HiddenInput()
            self.fields['status'].required = False  # make sure validation doesn't complain

    def clean_status(self):
        # If the user isn't allowed to edit, always return the original instance value
        if not self._can_edit_status and self.instance and self.instance.pk:
            return self.instance.status
        return self.cleaned_data.get('status')

        

from .utils import next_employee_id
from .models import UserProfile 

STAFFABLE_USER_TYPES = [
    ('staff', 'Staff'),
    ('receptionist', 'Receptionist'),
    ('cro', 'CRO'),
    ('operation_manager', 'Operations Manager'),
    ('pharmacy_manager', 'Pharmacy Manager'),
    ('doctor', 'Doctor'),
    ('consulting_doctor', 'Consulting Doctor'),
]


class StaffBaseForm(forms.ModelForm):
    user_type = forms.ChoiceField(
        choices=STAFFABLE_USER_TYPES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'is_active', 'user_type']
        widgets = {
            'username':   forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name':  forms.TextInput(attrs={'class': 'form-control'}),
            'email':      forms.EmailInput(attrs={'class': 'form-control'}),
            'is_active':  forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class StaffCreateForm(StaffBaseForm):
    password1 = forms.CharField(
        label="Password", widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    password2 = forms.CharField(
        label="Confirm Password", widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get('password1'), cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', "Passwords do not match.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.is_staff = True
        if user.user_type == "super_user":
            user.is_superuser = True

        if commit:
            user.save()

            # ✅ create profile + employee_id if needed
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if user.user_type in {
                "receptionist", "operation_manager", "pharmacy_manager",
                "staff", "cro", "consulting_doctor"
            } and not profile.employee_id:
                profile.employee_id = next_employee_id()
                profile.save(update_fields=["employee_id"])

        return user


class StaffEditForm(StaffBaseForm):
    new_password1 = forms.CharField(
        label="New Password", required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    new_password2 = forms.CharField(
        label="Confirm Password", required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get('new_password1') or '', cleaned.get('new_password2') or ''
        if p1 or p2:
            if p1 != p2:
                self.add_error('new_password2', "Passwords do not match.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)

        # ✅ reset password if provided
        p1 = self.cleaned_data.get('new_password1')
        if p1:
            user.set_password(p1)

        if commit:
            user.save()

            # ✅ ensure profile exists / assign employee_id if needed
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if user.user_type in {
                "receptionist", "operation_manager", "pharmacy_manager",
                "staff", "cro", "consulting_doctor"
            } and not profile.employee_id:
                profile.employee_id = next_employee_id()
                profile.save(update_fields=["employee_id"])

        return user
