from __future__ import annotations

from fastapi import APIRouter

from ..routes.academic import router as academic_router
from ..routes.activity_log import router as activity_log_router
from ..routes.auth import router as auth_router
from ..routes.application import router as application_router
from ..routes.appointment import router as appointment_router
from ..routes.attendance import router as attendance_router
from ..routes.audience_segment import router as audience_segment_router
from ..routes.comments import router as comments_router
from ..routes.communication import router as communication_router
from ..routes.contacts import router as contacts_router
from ..routes.departments import router as departments_router
from ..routes.document import router as document_router
from ..routes.duty import router as duty_router
from ..routes.email import router as email_router
from ..routes.employee_profile import router as employee_profile_router
from ..routes.employees import router as employees_router
from ..routes.health import router as health_router
from ..routes.integrations import router as integrations_router
from ..routes.job_role import router as job_role_router
from ..routes.leads import router as leads_router
from ..routes.leave import router as leave_router
from ..routes.notification import router as notification_router
from ..routes.notification_templates import router as notification_templates_router
from ..routes.offices import router as offices_router
from ..routes.onboarding import router as onboarding_router
from ..routes.organization import router as organization_router
from ..routes.payment import router as payment_router
from ..routes.payroll import router as payroll_router
from ..routes.permissions import router as permissions_router
from ..routes.platform import router as platform_router
from ..routes.report import router as report_router
from ..routes.resource import router as resource_router
from ..routes.student_profile import router as student_profile_router
from ..routes.task import router as task_router
from ..routes.users import router as users_router
from ..routes.whatsapp import router as whatsapp_router
from ..routes.whatsapp_webhook import router as whatsapp_webhook_router
from ..routes.workflow import router as workflow_router

router = APIRouter()

router.include_router(health_router)
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(student_profile_router)
router.include_router(employee_profile_router)
router.include_router(employees_router)
router.include_router(departments_router)
router.include_router(offices_router)
router.include_router(contacts_router)
router.include_router(attendance_router)
router.include_router(audience_segment_router)
router.include_router(leave_router)
router.include_router(payroll_router)
router.include_router(duty_router)
router.include_router(job_role_router)
router.include_router(resource_router)
router.include_router(report_router)
router.include_router(leads_router)
router.include_router(appointment_router)
router.include_router(document_router)
router.include_router(application_router)
router.include_router(payment_router)
router.include_router(notification_router)
router.include_router(notification_templates_router)
router.include_router(comments_router)
router.include_router(communication_router)
router.include_router(onboarding_router)
router.include_router(organization_router)
router.include_router(platform_router)
router.include_router(task_router)
router.include_router(academic_router)
router.include_router(workflow_router)
router.include_router(activity_log_router)
router.include_router(permissions_router)
router.include_router(integrations_router)
router.include_router(whatsapp_router)
router.include_router(email_router)
router.include_router(whatsapp_webhook_router)
