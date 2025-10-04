from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-oo8r5su^jionh6$krj7jy%zb=9@h(s^x^t90hez7a%w5ygfp$j'

DEBUG = True

ALLOWED_HOSTS = []

INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'dlappcrm.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'dlappcrm.wsgi.application'


# Database

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'dlappcrmdb',
        'USER' : 'root',
        'PASSWORD' : 'root'
    }
}


AUTH_USER_MODEL = 'core.User'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization

LANGUAGE_CODE = 'en-us'

USE_I18N = True

TIME_ZONE = 'Asia/Kolkata'
USE_TZ = True


STATIC_URL = 'static/'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

JAZZMIN_SETTINGS = {
    "site_title": "DLapp Admin",
    "site_header": "DLapp Administration",
    "site_brand": "Admin",
    "welcome_sign": "Welcome to DLapp Admin",
    "copyright": " DLapp Hair Regenerative Clinic",

    "site_logo": "assets/images/logo/dlapp_logo_grn.png",
    "login_logo": "assets/images/logo/dlapp_logo_grncut.png",

    # 👇 Control width (Bootstrap class)
    "login_logo_classes": "img-fluid",   # responsive
    "site_logo_classes": "img-fluid",    # same for sidebar

    # Optionally, use CSS style to force width
    "custom_css": "assets/css/custom_admin.css",

    "theme": "cosmo",
    "dark_mode_theme": "cyborg",

    "icons": {
        # Django auth
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.group": "fas fa-users",

        # Core app
        "core": "fas fa-clinic-medical",

        # User Management
        "core.user": "fas fa-user-md",
        "core.userprofile": "fas fa-user-cog",
        "core.employeeidsequence": "fas fa-id-card",

        # Patients
        "core.patient": "fas fa-user-injured",
        "core.patientmedicalhistory": "fas fa-notes-medical",

        # Consultations & Treatment
        "core.hairconsultation": "fas fa-microscope",
        "core.consultationphoto": "fas fa-camera",
        "core.treatmentplan": "fas fa-file-medical",
        "core.treatmentsession": "fas fa-procedures",
        "core.followup": "fas fa-clipboard-check",
        "core.progressphoto": "fas fa-images",

        # Appointments
        "core.appointment": "fas fa-calendar-check",
        "core.appointmentlog": "fas fa-history",
        "core.appointmentslot": "fas fa-clock",

        # Pharmacy & Inventory
        "core.medicinecategory": "fas fa-boxes",
        "core.medicine": "fas fa-pills",
        "core.medicinestock": "fas fa-capsules",
        "core.stocktransaction": "fas fa-exchange-alt",

        # Billing & Payments
        "core.bill": "fas fa-file-invoice",
        "core.billitem": "fas fa-file-invoice-dollar",
        "core.payment": "fas fa-credit-card",
        "core.service": "fas fa-concierge-bell",

        # Leads / CRO
        "core.leadsource": "fas fa-bullhorn",
        "core.lead": "fas fa-user-plus",

        # Expenses
        "core.expensecategory": "fas fa-list-alt",
        "core.expense": "fas fa-money-bill-wave",

        # Reports
        "core.dailyreport": "fas fa-chart-line",

        # Default fallbacks
        "default_icon_parents": "fas fa-chevron-circle-right",
        "default_icon_children": "fas fa-circle",
    }

}
