from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import RegexValidator
from decimal import Decimal
import uuid
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.db.models import F, Sum


# ===============================
# USER MANAGEMENT MODELS
# ===============================

class User(AbstractUser):
    USER_TYPE_CHOICES = [
        ('doctor', 'Doctor'),
        ('consulting_doctor', 'Consulting Doctor'),
        ('super_user', 'Super User'),
        ('operation_manager', 'Operation Manager'),
        ('pharmacy_manager', 'Pharmacy Manager'),
        ('receptionist', 'Receptionist'),
        ('staff', 'Staff'),
        ('cro', 'CRO'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES)
    phone_regex = RegexValidator(regex=r'^\+?1?\d{9,15}$')
    phone_number = models.CharField(validators=[phone_regex], max_length=17, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'users'
        verbose_name_plural = 'Users'

    def __str__(self):
        return self.get_full_name() or self.username
    
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    employee_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    department = models.CharField(max_length=100, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    date_of_joining = models.DateField(null=True, blank=True)
    salary = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    emergency_contact = models.CharField(max_length=17, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)
    
    class Meta:
        db_table = 'user_profiles'
        verbose_name_plural = 'User Profiles'

class EmployeeIdSequence(models.Model):
    year = models.PositiveIntegerField(unique=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'employee_id_sequences'
        verbose_name_plural = 'Employee ID Sequences'

# ===============================
# BRANCH MANAGEMENT MODELS
# ===============================

class Branch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150, unique=True)
    phone_number = models.CharField(max_length=17, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'branches'
        ordering = ['name']
        verbose_name_plural = 'Branches'

    def __str__(self):
        return self.name


# ===============================
# PATIENT MANAGEMENT MODELS
# ===============================
class Patient(models.Model):
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('others', 'Others'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file_number = models.CharField(max_length=20, unique=True, blank=True)
    name = models.CharField(max_length=200)
    age = models.PositiveIntegerField()
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    phone_number = models.CharField(max_length=17)
    email = models.EmailField(blank=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10, blank=True)
    occupation = models.CharField(max_length=100, blank=True)

    referred_by = models.CharField(max_length=200, blank=True)
    referral_source = models.CharField(max_length=200, blank=True)
    emergency_contact_name = models.CharField(max_length=200, blank=True)
    emergency_contact_phone = models.CharField(max_length=17, blank=True)

    registered_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, related_name='registered_patients')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    # 👉 Persistent running balance
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    # > 0 = Due, < 0 = Advance

    class Meta:
        db_table = 'patients'
        verbose_name_plural = 'Patients'

    def save(self, *args, **kwargs):
        if not self.file_number:
            year = timezone.now().year
            count = Patient.objects.filter(created_at__year=year).count() + 1
            self.file_number = f"DLP{year}{count:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.file_number})" if self.file_number else self.name

# Services

class Service(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=30, unique=True, blank=True)  # optional SKU
    name = models.CharField(max_length=200, unique=True)
    default_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "services"
        ordering = ["name"]
        verbose_name_plural = 'Services'

    def __str__(self):
        return self.name


    def save(self, *args, **kwargs):
        if not self.code:
            prefix = "SRV"
            n = 1
            last = Service.objects.exclude(code="").order_by("-created_at").first()
            if last and last.code.startswith(prefix) and last.code[len(prefix):].isdigit():
                n = int(last.code[len(prefix):]) + 1
            # ensure uniqueness even if race (simple loop)
            while Service.objects.filter(code=f"{prefix}{n:04d}").exists():
                n += 1
            self.code = f"{prefix}{n:04d}"
        super().save(*args, **kwargs)



class PatientMedicalHistory(models.Model):
    patient = models.OneToOneField(Patient, on_delete=models.CASCADE, related_name='medical_history')
    
    # Medical Conditions
    hypertension = models.BooleanField(default=False)
    hypertension_family = models.BooleanField(default=False)
    diabetes = models.BooleanField(default=False)
    diabetes_family = models.BooleanField(default=False)
    thyroid_disorder = models.BooleanField(default=False)
    thyroid_disorder_family = models.BooleanField(default=False)
    autoimmune_disease = models.BooleanField(default=False)
    autoimmune_disease_family = models.BooleanField(default=False)
    allergies = models.BooleanField(default=False)
    allergies_family = models.BooleanField(default=False)
    
    # Specific Details
    allergy_details = models.TextField(blank=True)
    current_medications = models.TextField(blank=True)
    surgical_history = models.TextField(blank=True)
    other_conditions = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'patient_medical_history'
        verbose_name_plural = 'Patient Medical Histories'

# ===============================
# HAIR CONSULTATION MODELS
# ===============================

class HairConsultation(models.Model):
    SCALP_CONDITION_CHOICES = [
        ('normal', 'Normal'),
        ('oily', 'Oily'),
        ('dry', 'Dry'),
        ('dandruff', 'Dandruff'),
        ('inflammation', 'Inflammation'),
    ]
    
    PULL_TEST_CHOICES = [
        ('positive', 'Positive'),
        ('negative', 'Negative'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='consultations')
    consultation_date = models.DateTimeField(auto_now_add=True)
    doctor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='consultations')
    
    # Chief Complaint
    hair_loss_onset = models.CharField(max_length=200, blank=True)
    hair_loss_duration = models.CharField(max_length=100, blank=True)
    affected_area = models.TextField(blank=True)
    associated_symptoms = models.TextField(blank=True)
    previous_treatments = models.TextField(blank=True)
    
    # Examination
    scalp_condition = models.CharField(max_length=20, choices=SCALP_CONDITION_CHOICES, blank=True)
    hair_density = models.CharField(max_length=100, blank=True)
    miniaturization_grade = models.CharField(max_length=100, blank=True)
    pull_test = models.CharField(max_length=10, choices=PULL_TEST_CHOICES, blank=True)
    dermoscopy_findings = models.TextField(blank=True)
    
    # Educational Images
    scalp_zones_image = models.ImageField(upload_to='consultation/scalp_zones/', null=True, blank=True)
    hair_patterns_image = models.ImageField(upload_to='consultation/hair_patterns/', null=True, blank=True)
    
    # Doctor's Remarks
    examination_remarks = models.TextField(blank=True)
    
    class Meta:
        db_table = 'hair_consultations'
        verbose_name_plural = 'Hair Consultations'
    
    def __str__(self):
        return f"{self.patient.name} - {self.consultation_date.strftime('%Y-%m-%d')}"

class ConsultationPhoto(models.Model):
    PHOTO_TYPE_CHOICES = [
        ('frontal_before', 'Frontal Before'),
        ('vertex_before', 'Vertex Before'),
        ('frontal_after', 'Frontal After'),
        ('vertex_after', 'Vertex After'),
    ]
    
    consultation = models.ForeignKey(HairConsultation, on_delete=models.CASCADE, related_name='photos')
    photo_type = models.CharField(max_length=20, choices=PHOTO_TYPE_CHOICES)
    image = models.ImageField(upload_to='consultation/photos/')
    notes = models.TextField(blank=True)
    taken_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'consultation_photos'
        unique_together = ['consultation', 'photo_type']
        verbose_name_plural = 'Consultation Photos'

# ===============================
# TREATMENT MODELS
# ===============================

class TreatmentPlan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consultation = models.OneToOneField(HairConsultation, on_delete=models.CASCADE, related_name='treatment_plan')

    # Diagnosis
    primary_diagnosis = models.TextField()
    differential_factors = models.TextField(blank=True)

    # Treatment Details
    procedure = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="treatment_plans")
    session_frequency = models.CharField(max_length=100)  # e.g., "every 4 weeks"
    total_sessions = models.PositiveIntegerField()
    adjunctive_treatments = models.TextField(blank=True)

    # Consent & Timeline
    expected_outcomes_explained = models.BooleanField(default=False)
    consent_obtained = models.BooleanField(default=False)

    # Pricing
    cost_per_session = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        db_table = 'treatment_plans'
        verbose_name_plural = 'Treatment Plans'

    def save(self, *args, **kwargs):
        self.total_cost = self.cost_per_session * self.total_sessions
        super().save(*args, **kwargs)

# ===============================
# APPOINTMENT & SESSION MODELS
# ===============================

class Appointment(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('rescheduled', 'Rescheduled')
    ]

    SITTINGS_CHOICES = [
        ('consultation', 'Consultation'),
        ('first', 'First Sitting'),
        ('second', 'Second Sitting'),
        ('boost', 'Booster'),
        ('repeat_first', 'Repeat First'),
        ('repeat_second', 'Repeat Second'),
        ('gfc', 'GFC'),
        ('other', 'Other'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='appointments')
    treatment_plan = models.ForeignKey(TreatmentPlan, on_delete=models.SET_NULL, null=True, blank=True)
    sittings = models.CharField(max_length=20, choices=SITTINGS_CHOICES, default='consultation')
    
    appointment_date = models.DateTimeField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='scheduled')
    
    assigned_doctor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='doctor_appointments')
    branch = models.ForeignKey('Branch', on_delete=models.PROTECT, related_name='appointments', null=True, blank=True)
    notes = models.TextField(blank=True)
    reminder_sent = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_appointments')
    
    class Meta:
        db_table = 'appointments'
        ordering = ['appointment_date']
        verbose_name_plural = 'Appointments'

    def __str__(self):
        return f"Appointment for {self.patient.name} on {self.appointment_date.strftime('%Y-%m-%d %H:%M')}"
    
class AppointmentLog(models.Model):
    class Meta:
        verbose_name_plural = 'Appointment Logs'
    ACTIONS = [
        ('create', 'Create'),
        ('reschedule', 'Reschedule'),
        ('cancel', 'Cancel'),
        ('complete', 'Complete'),
    ]
    appointment = models.ForeignKey('Appointment', on_delete=models.CASCADE, related_name='logs')
    by          = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
    action      = models.CharField(max_length=20, choices=ACTIONS)
    at          = models.DateTimeField(auto_now_add=True)

    from_datetime = models.DateTimeField(null=True, blank=True)
    to_datetime   = models.DateTimeField(null=True, blank=True)
    from_status   = models.CharField(max_length=20, blank=True, default='')
    to_status     = models.CharField(max_length=20, blank=True, default='')
    note          = models.TextField(blank=True, default='')

class TreatmentSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='session')
    treatment_plan = models.ForeignKey(TreatmentPlan, on_delete=models.CASCADE, related_name='sessions')
    session_number = models.PositiveIntegerField()
    
    # Session Details
    procedure_performed = models.CharField(max_length=200)
    parameters_dosage = models.TextField(blank=True)  # Dosage, settings, etc.
    scalp_prep_anesthesia = models.TextField(blank=True)
    observations_during_procedure = models.TextField(blank=True)
    immediate_post_care = models.TextField(blank=True)
    
    # Adverse Events
    adverse_events = models.BooleanField(default=False)
    adverse_event_details = models.TextField(blank=True)
    
    # Medications/Topicals
    medications_prescribed = models.TextField(blank=True)
    next_appointment_date = models.DateTimeField(null=True, blank=True)
    
    # Staff Information
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='performed_sessions')
    clinician_initials = models.CharField(max_length=10, blank=True)
    
    # Session Photos
    before_photo = models.ImageField(upload_to='sessions/before/', null=True, blank=True)
    after_photo = models.ImageField(upload_to='sessions/after/', null=True, blank=True)
    
    # Remarks
    session_remarks = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'treatment_sessions'
        unique_together = ['treatment_plan', 'session_number']
        verbose_name_plural = 'Treatment Sessions'

# ===============================
# FOLLOW-UP & PROGRESS MODELS
# ===============================

class FollowUp(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='followups')
    treatment_plan = models.ForeignKey(TreatmentPlan, on_delete=models.CASCADE,
                                       related_name='followups', null=True, blank=True)
    
    # Change these fields from DateTimeField to DateField
    followup_date = models.DateField() 
    overall_response_percentage = models.PositiveIntegerField()
    patient_satisfaction = models.PositiveIntegerField()
    
    future_recommendations = models.TextField()
    maintenance_plan = models.TextField(blank=True)
    
    # Progress Photos
    progress_photos = models.ManyToManyField('ProgressPhoto', blank=True)
    
    doctor_remarks = models.TextField(blank=True)
    # Change this field to DateField
    next_followup_date = models.DateField(null=True, blank=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'followups'
        verbose_name_plural = 'Follow Ups'

class ProgressPhoto(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    image = models.ImageField(upload_to='progress/')
    photo_type = models.CharField(max_length=50)  # frontal, vertex, etc.
    taken_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'progress_photos'
        verbose_name_plural = 'Progress Photos'

# ===============================
# INVENTORY & PHARMACY MODELS
# ===============================

class MedicineCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'medicine_categories'
        verbose_name_plural = 'Medicine Categories'
    
    def __str__(self):
        return self.name

class Medicine(models.Model):
    MEDICINE_TYPE_CHOICES = [
        ('tablet', 'Tablet'),
        ('capsule', 'Capsule'),
        ('syrup', 'Syrup'),
        ('injection', 'Injection'),
        ('topical', 'Topical'),
        ('solution', 'Solution'),
        ('other', 'Other'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    generic_name = models.CharField(max_length=200, blank=True)
    category = models.ForeignKey(MedicineCategory, on_delete=models.SET_NULL, null=True)
    medicine_type = models.CharField(max_length=20, choices=MEDICINE_TYPE_CHOICES)
    strength = models.CharField(max_length=50, blank=True)  # e.g., "500mg", "10ml"
    manufacturer = models.CharField(max_length=200, blank=True)
    
    # Pricing
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Stock Management
    minimum_stock_level = models.PositiveIntegerField(default=10)
    unit_of_measurement = models.CharField(max_length=20, default='pieces') 
    
    # Additional Info
    description = models.TextField(blank=True)
    side_effects = models.TextField(blank=True)
    contraindications = models.TextField(blank=True)
    storage_instructions = models.TextField(blank=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        db_table = 'medicines'
        verbose_name_plural = 'Medicines'
    
    def __str__(self):
        return f"{self.name} ({self.strength})"

class MedicineStock(models.Model):
    medicine = models.OneToOneField(Medicine, on_delete=models.CASCADE, related_name='stock')
    current_quantity = models.PositiveIntegerField(default=0)
    reserved_quantity = models.PositiveIntegerField(default=0)  # For pending orders
    last_updated = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        db_table = 'medicine_stocks'
        verbose_name_plural = 'Medicine Stocks'
    
    @property
    def available_quantity(self):
        return self.current_quantity - self.reserved_quantity
    
    @property
    def is_low_stock(self):
        return self.current_quantity <= self.medicine.minimum_stock_level

class StockTransaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('purchase', 'Purchase'),
        ('sale', 'Sale'),
        ('adjustment', 'Adjustment'),
        ('expired', 'Expired'),
        ('damaged', 'Damaged'),
        ('return', 'Return'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=15, choices=TRANSACTION_TYPE_CHOICES)
    quantity = models.IntegerField()  
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Batch Information
    batch_number = models.CharField(max_length=50, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    supplier = models.CharField(max_length=200, blank=True)
    
    # Reference Information
    reference_number = models.CharField(max_length=100, blank=True)
    patient = models.ForeignKey(Patient, on_delete=models.SET_NULL, null=True, blank=True)
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)


    class Meta:
        db_table = 'stock_transactions'
        ordering = ['-created_at']
        verbose_name_plural = 'Stock Transactions'

    IN_TYPES = {'purchase', 'return'}
    OUT_TYPES = {'sale', 'expired', 'damaged'}

    def _normalize_quantity_sign(self):
        """Force correct sign based on transaction_type."""
        if self.transaction_type in self.IN_TYPES:
            # incoming must be positive
            self.quantity = abs(self.quantity or 0)
        elif self.transaction_type in self.OUT_TYPES:
            # outgoing must be negative
            self.quantity = -abs(self.quantity or 0)

    def save(self, *args, **kwargs):
        self._normalize_quantity_sign()
        super().save(*args, **kwargs)

# ===============================
# BILLING & PAYMENT MODELS
# ===============================
from decimal import Decimal
from django.utils import timezone

class Bill(models.Model):
    BILL_TYPE = [('service', 'Service'), ('pharmacy', 'Pharmacy')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bill_number = models.CharField(max_length=20, unique=True, blank=True)

    patient = models.ForeignKey('Patient', on_delete=models.CASCADE, related_name='bills')
    bill_type = models.CharField(max_length=10, choices=BILL_TYPE, default='service')
    bill_date = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    remark = models.TextField(blank=True, default='')
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True)

    class Meta:
        db_table = 'bills'
        ordering = ['-bill_date']
        verbose_name_plural = 'Bills'

    def __str__(self):
        return self.bill_number or (f"Bill for {self.patient.name}" if self.patient_id else "Bill")

    def save(self, *args, **kwargs):
        # CRITICAL: Only update patient balance when explicitly requested
        update_patient_balance = kwargs.pop('update_patient_balance', False)
        
        # Correctly detect first save
        creating = self._state.adding or not type(self).objects.filter(pk=self.pk).exists()

        # Calculate balance delta only if requested
        balance_delta = Decimal('0.00')
        if update_patient_balance and self.patient_id:
            if creating:
                balance_delta = self.total_amount or Decimal('0.00')
            else:
                old_total = type(self).objects.only('total_amount').get(pk=self.pk).total_amount or Decimal('0.00')
                balance_delta = (self.total_amount or Decimal('0.00')) - old_total

        # Generate bill number on create
        if creating and not self.bill_number:
            year = timezone.now().year
            count = type(self).objects.filter(bill_date__year=year).count() + 1
            self.bill_number = f"INV{year}{count:06d}"

        super().save(*args, **kwargs)

        # Update patient balance ONLY when explicitly requested
        if update_patient_balance and self.patient_id and balance_delta != 0:
            type(self.patient).objects.filter(pk=self.patient_id).update(
                balance=F('balance') + balance_delta
            )

    def recalculate(self, save=True):
        total = self.items.aggregate(s=Sum('total_price'))['s'] or Decimal('0.00')
        self.total_amount = total

        if save:
            self.save(update_fields=['total_amount', 'updated_at'])

        return total


class BillItem(models.Model):
    ITEM_KIND = [('service', 'Service'), ('pharmacy', 'Medicine')]

    bill = models.ForeignKey('Bill', on_delete=models.CASCADE, related_name='items')
    kind = models.CharField(max_length=10, choices=ITEM_KIND)

    service = models.ForeignKey('Service', on_delete=models.PROTECT, null=True, blank=True, related_name='bill_items')
    medicine = models.ForeignKey('Medicine', on_delete=models.PROTECT, null=True, blank=True, related_name='bill_items')

    description = models.CharField(max_length=200, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        db_table = 'bill_items'
        verbose_name_plural = 'Bill Items'

    def clean(self):
        if self.kind == 'service':
            if not self.service:
                raise ValidationError("Select a service for a service item.")
            self.medicine = None
            if not self.description:
                self.description = self.service.name
            if not self.unit_price or self.unit_price == 0:
                self.unit_price = self.service.default_price or Decimal('0.00')

        elif self.kind == 'pharmacy':
            if not self.medicine:
                raise ValidationError("Select a medicine for a pharmacy item.")
            self.service = None
            if not self.description:
                name = self.medicine.name
                self.description = f"{name}{f' ({self.medicine.strength})' if self.medicine.strength else ''}"
            if not self.unit_price or self.unit_price == 0:
                self.unit_price = self.medicine.selling_price or Decimal('0.00')

        if not self.quantity or self.quantity <= 0:
            raise ValidationError("Quantity must be > 0.")

    def save(self, *args, **kwargs):
        # Set line total
        self.total_price = (self.unit_price or Decimal('0.00')) * (self.quantity or 0)

        # Compute delta vs previous value to update bill.total_amount
        if self._state.adding or not type(self).objects.filter(pk=self.pk).exists():
            delta = self.total_price
        else:
            old = type(self).objects.only('total_price').get(pk=self.pk)
            delta = self.total_price - (old.total_price or Decimal('0.00'))

        # Update parent bill total (NEVER update patient balance here)
        self.bill.total_amount = (self.bill.total_amount or Decimal('0.00')) + delta
        self.bill.save(update_fields=['total_amount', 'updated_at'])  # No balance update

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Reduce parent total (NEVER update patient balance here)
        self.bill.total_amount = (self.bill.total_amount or Decimal('0.00')) - (self.total_price or Decimal('0.00'))
        self.bill.save(update_fields=['total_amount', 'updated_at'])  # No balance update
        super().delete(*args, **kwargs)


class Payment(models.Model):
    class Meta:
        verbose_name_plural = 'Payments'
    PAYMENT_METHOD_CHOICES = [('cash', 'Cash'), ('card', 'Card'), ('upi', 'UPI'), ('cheque', 'Cheque')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey('Patient', on_delete=models.CASCADE, related_name='payments')
    bill = models.ForeignKey('Bill', related_name='payments', on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=50, choices=PAYMENT_METHOD_CHOICES)
    date = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        D0 = Decimal('0.00')

        creating = self._state.adding or not type(self).objects.filter(pk=self.pk).exists()
        if creating:
            old_amount = D0
        else:
            old_amount = type(self).objects.only('amount').get(pk=self.pk).amount or D0

        delta = (self.amount or D0) - old_amount

        super().save(*args, **kwargs)

        # Payment reduces patient balance (increases payment/advance)
        if self.patient_id and delta != D0:
            type(self.patient).objects.filter(pk=self.patient_id).update(
                balance=F('balance') - delta
            )

    def delete(self, *args, **kwargs):
        # When payment is deleted, add the amount back to patient balance
        if self.patient_id and self.amount:
            type(self.patient).objects.filter(pk=self.patient_id).update(
                balance=F('balance') + self.amount
            )
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.amount} ({self.method}) for {self.patient.name}"




# ===============================
# LEAD MANAGEMENT MODELS (for CRO)
# ===============================

class LeadSource(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'lead_sources'
        verbose_name_plural = 'Lead Sources'
    
    def __str__(self):
        return self.name

class Lead(models.Model):
    LEAD_SOURCE_CHOICES = [
        ('instagram', 'Instagram'),
        ('youtube', 'YouTube'),
        ('facebook', 'Facebook'),
        ('website', 'Website'),
        ('referral', 'Referral'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=17)
    email = models.EmailField(blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    
    lead_source = models.ForeignKey(LeadSource, on_delete=models.SET_NULL, null=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    
    
    # CRO Management
    last_contact_date = models.DateField(null=True, blank=True)
    next_followup_date = models.DateField(null=True, blank=True)
    
    # Conversion
    converted_patient = models.OneToOneField(Patient, on_delete=models.SET_NULL, null=True, blank=True)
    conversion_date = models.DateField(null=True, blank=True)
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_leads')
    
    class Meta:
        db_table = 'leads'
        ordering = ['-created_at']
        verbose_name_plural = 'Leads'
    
    def __str__(self):
        return f"{self.name} - {self.phone_number}"
    
    def convert_to_patient(self, registered_by=None):
        from .models import Patient  # local import to avoid circular
        if self.converted_patient_id:
            return self.converted_patient  # already converted

        with transaction.atomic():
            patient = Patient.objects.create(
                name=self.name,
                age=self.age or 0,
                date_of_birth=timezone.now().date().replace(year=timezone.now().year- (self.age or 0)) if self.age else timezone.now().date(),
                gender='male',  # or leave blank if you make it nullable later
                phone_number=self.phone_number,
                email=self.email or "",
                address=self.location or "",
                city="",
                district="",
                pincode="",
                registered_by=registered_by,
            )
            self.converted_patient = patient
            self.conversion_date = timezone.now()
            self.save(update_fields=['converted_patient','conversion_date'])
            return patient

# ===============================
# EXPENSE MANAGEMENT MODELS
# ===============================

class ExpenseCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'expense_categories'
        verbose_name_plural = 'Expense Categories'
    
    def __str__(self):
        return self.name

class Expense(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('paid', 'Paid'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    expense_number = models.CharField(max_length=20, unique=True, blank=True)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True)
    
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    expense_date = models.DateField()
    
    # Supporting Documents
    attachment = models.ImageField(upload_to='expenses/receipts/', null=True, blank=True)
    invoice_number = models.CharField(max_length=100, blank=True)
    vendor_name = models.CharField(max_length=200, blank=True)
    
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True)
    
    # Approval Process
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='requested_expenses')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_expenses')
    approval_date = models.DateTimeField(null=True, blank=True)
    approval_notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'expenses'
        ordering = ['-expense_date']
        verbose_name_plural = 'Expenses'
    
    def save(self, *args, **kwargs):
        if not self.expense_number:
            from django.utils import timezone
            year = timezone.now().year
            count = Expense.objects.filter(created_at__year=year).count() + 1
            self.expense_number = f"EXP{year}{count:05d}"
        super().save(*args, **kwargs)

# ===============================
# REPORTING & ANALYTICS MODELS
# ===============================

class DailyReport(models.Model):
    report_date = models.DateField(unique=True)
    
    # Patient Statistics
    new_patients = models.PositiveIntegerField(default=0)
    total_appointments = models.PositiveIntegerField(default=0)
    completed_appointments = models.PositiveIntegerField(default=0)
    cancelled_appointments = models.PositiveIntegerField(default=0)
    
    # Financial Statistics
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cash_collection = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    card_collection = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    outstanding_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Treatment Statistics
    prp_sessions = models.PositiveIntegerField(default=0)
    mesotherapy_sessions = models.PositiveIntegerField(default=0)
    lllt_sessions = models.PositiveIntegerField(default=0)
    other_treatments = models.PositiveIntegerField(default=0)
    
    # Medicine Statistics
    medicine_sales_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        db_table = 'daily_reports'
        ordering = ['-report_date']
        verbose_name_plural = 'Daily Reports'

