from enum import Enum


class UserRole(str, Enum):
    STUDENT = "student"
    COUNSELLOR = "counsellor"
    FRONTDESK = "frontdesk"
    STAFF = "staff"
    FINANCE = "finance"
    MARKETING = "marketing"
    SUPPORT = "support"
    ADMISSIONS = "admissions"
    MANAGER = "manager"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"
    VIEWER = "viewer"


class OrganizationStatus(str, Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class InstitutionType(str, Enum):
    BACHELOR = "bachelor"
    DIPLOMA = "diploma"
    _10_2 = "10+2"
    MASTERS = "masters"


class LeadStatus(str, Enum):
    NEW = "new"
    CONTACTED = "contacted"
    FOLLOW_UP = "follow_up"
    QUALIFIED = "qualified"
    CONVERTED = "converted"
    LOST = "lost"


class LeadSource(str, Enum):
    WEBSITE = "website"
    WALK_IN = "walk_in"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    GOOGLE = "google"
    TIKTOK = "tiktok"
    LINKEDIN = "linkedin"
    WHATSAPP = "whatsapp"
    PHONE = "phone"
    REFERRAL = "referral"
    EVENT = "event"
    OTHER = "other"


class DocumentType(str, Enum):
    PASSPORT = "passport"
    CITIZENSHIP = "citizenship"
    NATIONAL_ID = "national_id"
    ACADEMIC_TRANSCRIPT = "academic_transcript"
    ACADEMIC_CERTIFICATE = "academic_certificate"
    PROVISIONAL_CERTIFICATE = "provisional_certificate"
    CHARACTER_CERTIFICATE = "character_certificate"
    ENGLISH_TEST = "english_test"
    CV = "cv"
    STATEMENT_OF_PURPOSE = "statement_of_purpose"
    RECOMMENDATION_LETTER = "recommendation_letter"
    OFFER_LETTER = "offer_letter"
    VISA = "visa"
    FINANCIAL_DOCUMENT = "financial_document"
    MEDICAL_REPORT = "medical_report"
    PHOTO = "photo"
    OTHER = "other"


class DocumentStatus(str, Enum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class LeadActivityType(str, Enum):
    LEAD_CREATED = "lead_created"
    CALL = "call"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    MEETING = "meeting"
    NOTE = "note"
    STATUS_CHANGED = "status_changed"
    ASSIGNED = "assigned"
    FOLLOW_UP = "follow_up"
    DOCUMENT_RECEIVED = "document_received"
    CONVERTED = "converted"
    LOST = "lost"


class ApplicationStatus(str, Enum):
    DRAFT = "draft"
    DOCUMENTS_PENDING = "documents_pending"
    READY_TO_SUBMIT = "ready_to_submit"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    OFFER_RECEIVED = "offer_received"
    OFFER_ACCEPTED = "offer_accepted"
    OFFER_DECLINED = "offer_declined"
    VISA_PROCESSING = "visa_processing"
    VISA_APPROVED = "visa_approved"
    VISA_REJECTED = "visa_rejected"
    ENROLLED = "enrolled"
    WITHDRAWN = "withdrawn"
    REJECTED = "rejected"


class AppointmentStatus(str, Enum):
    REQUESTED = "requested"
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    RESCHEDULED = "rescheduled"


class AppointmentType(str, Enum):
    CONSULTATION = "consultation"
    DOCUMENT_REVIEW = "document_review"
    APPLICATION_REVIEW = "application_review"
    VISA_CONSULTATION = "visa_consultation"
    FOLLOW_UP = "follow_up"
    PHONE_CALL = "phone_call"
    VIDEO_CALL = "video_call"
    OFFICE_VISIT = "office_visit"
    OTHER = "other"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    FOLLOW_UP = "follow_up"
    DOCUMENT_COLLECTION = "document_collection"
    DOCUMENT_VERIFICATION = "document_verification"
    APPLICATION_SUBMISSION = "application_submission"
    VISA_PROCESSING = "visa_processing"
    PAYMENT_FOLLOW_UP = "payment_follow_up"
    APPOINTMENT = "appointment"
    CALL = "call"
    EMAIL = "email"
    OTHER = "other"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class PaymentMethod(str, Enum):
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    ESewa = "esewa"
    KHALTI = "khalti"
    FONEPAY = "fonepay"
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    OTHER = "other"


class SubscriptionPlan(str, Enum):
    FREE = "free"
    PREMIUM = "premium"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class OrgSubscriptionPlan(str, Enum):
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class OrgSubscriptionStatus(str, Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"


class BillingCycle(str, Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class NotificationType(str, Enum):
    SYSTEM = "system"
    APPLICATION = "application"
    PAYMENT = "payment"
    APPOINTMENT = "appointment"
    TASK = "task"
    DOCUMENT = "document"
    LEAD = "lead"
    FOLLOW_UP_DUE = "follow_up_due"
    APPLICANT = "applicant"
    WHATSAPP = "whatsapp"
    EMAIL = "email"


class NotificationChannel(str, Enum):
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"


class CommentEntityType(str, Enum):
    LEAD = "lead"
    APPLICANT = "applicant"
    APPLICATION = "application"
    # Reused as WhatsApp's "internal note" store (spec: internal notes must
    # never be sent to WhatsApp, and must be visually distinct from the
    # message thread) — rather than building a second notes system.
    WHATSAPP_CONVERSATION = "whatsapp_conversation"
    # Same idea for email threads — internal notes never get sent as mail.
    EMAIL_THREAD = "email_thread"


class NotificationTemplateKey(str, Enum):
    """The 8 editable message templates configured on the Settings > Email
    Templates page. Deliberately separate from NotificationType (which keeps
    categorizing notifications for topbar UI/icon purposes) — a template key
    identifies WHICH configurable message was used, not what kind of entity
    the notification is about."""

    LEAD_WELCOME = "lead_welcome"
    FOLLOW_UP_REMINDER = "follow_up_reminder"
    APPLICATION_SUBMITTED = "application_submitted"
    OFFER_RECEIVED = "offer_received"
    DOCUMENT_REQUIRED = "document_required"
    VISA_UPDATE = "visa_update"
    PAYMENT_REMINDER = "payment_reminder"
    STAFF_NOTIFICATION = "staff_notification"


class CommunicationKind(str, Enum):
    INTERNAL = "internal"
    STUDENT = "student"


# --- WhatsApp Business Cloud API integration --------------------------------
# See models/whatsapp.py and models/integration.py-equivalent (Integration
# lives in whatsapp.py too, since it's the only integration provider today —
# see that file's module docstring for why it's still modeled generically).


class IntegrationProvider(str, Enum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"


class IntegrationStatus(str, Enum):
    NOT_CONNECTED = "not_connected"
    CONNECTED = "connected"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class WhatsAppContactEntityType(str, Enum):
    """Which CRM record a WhatsApp contact has been matched to — same
    polymorphic-pointer convention as CommentEntityType (see comment.py)."""

    LEAD = "lead"
    STUDENT = "student"


class WhatsAppMessageDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class WhatsAppMessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    DOCUMENT = "document"
    TEMPLATE = "template"
    VIDEO = "video"
    AUDIO = "audio"


class WhatsAppMessageStatus(str, Enum):
    """Outbound-only — inbound messages have no status column value (nothing
    to track: they already arrived). Meta's own terminology, in order."""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class WhatsAppTemplateStatus(str, Enum):
    """Mirrors Meta's own template review statuses."""

    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"
    PAUSED = "paused"


# --- Gmail email integration --------------------------------------------
# Mirrors the WhatsApp integration's shape (Integration row with
# provider=EMAIL, a dedicated account/contact/thread/message set) — see
# models/email.py. Sync is polling-based (Gmail history.list), not
# webhook-based, since Gmail push requires a separate Google Cloud Pub/Sub
# setup this codebase deliberately avoids (see gmail_client.py docstring).


class EmailContactEntityType(str, Enum):
    """Which CRM record an email contact has been matched to — same
    polymorphic-pointer convention as WhatsAppContactEntityType."""

    LEAD = "lead"
    STUDENT = "student"


class EmailMessageDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class EmailMessageStatus(str, Enum):
    """Outbound-only. No DELIVERED/READ states like WhatsApp has — Gmail's
    API gives us no delivery or read-receipt signal for sent mail."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class ActivityType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    ASSIGN = "assign"
    STATUS_CHANGE = "status_change"
    PAYMENT = "payment"
    IMPERSONATE = "impersonate"
    OTHER = "other"


class DegreeLevel(str, Enum):
    CERTIFICATE = "certificate"
    DIPLOMA = "diploma"
    ADVANCED_DIPLOMA = "advanced_diploma"
    BACHELOR = "bachelor"
    POSTGRADUATE_DIPLOMA = "postgraduate_diploma"
    MASTER = "master"
    DOCTORATE = "doctorate"


class EnglishTestType(str, Enum):
    IELTS = "ielts"
    PTE = "pte"
    TOEFL = "toefl"
    DUOLINGO = "duolingo"
    OTHER = "other"


class WorkflowStepStatus(str, Enum):
    PENDING = "pending"
    CURRENT = "current"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class WorkflowActivityType(str, Enum):
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    NOTE_ADDED = "note_added"
    ASSIGNED = "assigned"
    DOCUMENT_LINKED = "document_linked"
    COMMENT = "comment"


class ApplicationWorkflowStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ChecklistItemStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    REJECTED = "rejected"
    WAIVED = "waived"


class LeadPriority(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class FollowUpMethod(str, Enum):
    PHONE_CALL = "phone_call"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    SMS = "sms"
    IN_PERSON = "in_person"
    VIDEO_MEETING = "video_meeting"


class FollowUpOutcome(str, Enum):
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    CALL_BACK_LATER = "call_back_later"
    INTERESTED = "interested"
    VERY_INTERESTED = "very_interested"
    DOCUMENTS_PENDING = "documents_pending"
    THINKING = "thinking"
    WRONG_NUMBER = "wrong_number"
    NOT_ELIGIBLE = "not_eligible"
    DUPLICATE = "duplicate"
    CONVERTED_TO_PROSPECT = "converted_to_prospect"
    CONVERTED_TO_CLIENT = "converted_to_client"


class LostReason(str, Enum):
    NO_RESPONSE_AFTER_7_ATTEMPTS = "no_response_after_7_attempts"
    NOT_INTERESTED = "not_interested"
    BUDGET_ISSUE = "budget_issue"
    CHOSE_ANOTHER_CONSULTANCY = "chose_another_consultancy"
    WRONG_NUMBER = "wrong_number"
    INVALID_LEAD = "invalid_lead"
    NOT_ELIGIBLE = "not_eligible"
    DUPLICATE_LEAD = "duplicate_lead"
    OTHER = "other"


class ConversionSource(str, Enum):
    AGREEMENT_SIGNED = "agreement_signed"
    SERVICE_PURCHASED = "service_purchased"
    REGISTRATION_COMPLETED = "registration_completed"
    PAYMENT_RECEIVED = "payment_received"
    OTHER = "other"


class EmploymentType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERN = "intern"
    FREELANCE = "freelance"


class EmploymentEventType(str, Enum):
    """Deliberately small — covers what Phase 1 (People foundation) actually
    writes. Extend with new values (e.g. salary_changed, leave_started) via an
    additive `ALTER TYPE ... ADD VALUE` migration when Payroll/Leave land,
    same pattern as AppointmentStatus.REQUESTED earlier."""

    JOINED = "joined"
    PROMOTED = "promoted"
    DEPARTMENT_CHANGED = "department_changed"
    MANAGER_CHANGED = "manager_changed"
    DESIGNATION_CHANGED = "designation_changed"
    STATUS_CHANGED = "status_changed"
    PROBATION_COMPLETED = "probation_completed"
    CONTRACT_RENEWED = "contract_renewed"
    SALARY_CHANGED = "salary_changed"
    OTHER = "other"


class AttendanceStatus(str, Enum):
    """Only PRESENT/LATE/HALF_DAY/ON_LEAVE/HOLIDAY are ever written to a row
    by application code. ABSENT and WEEKEND are computed at query time
    (nobody has a row for that day) and only exist here so the same enum can
    describe a computed cell in the dashboard/summary response."""

    PRESENT = "present"
    LATE = "late"
    HALF_DAY = "half_day"
    ON_LEAVE = "on_leave"
    HOLIDAY = "holiday"
    ABSENT = "absent"
    WEEKEND = "weekend"


class AttendanceSource(str, Enum):
    WEB = "web"
    MANUAL = "manual"


class LeaveStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class PayrollRunStatus(str, Enum):
    DRAFT = "draft"
    FINALIZED = "finalized"
    PAID = "paid"


class PayslipLineType(str, Enum):
    ADDITION = "addition"
    DEDUCTION = "deduction"


class ContactType(str, Enum):
    PARTNER = "partner"
    AGENT = "agent"
    VENDOR = "vendor"
    OTHER = "other"
