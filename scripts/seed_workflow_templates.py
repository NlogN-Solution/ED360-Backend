"""Idempotent seed for default + country-specific workflow templates.

Run with: .venv/bin/python -m scripts.seed_workflow_templates

Safe to re-run — every insert is guarded by a lookup on a unique key (country iso2,
template slug, stage key within a template), so re-running only fills in what's
missing rather than duplicating rows.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from sqlalchemy import select

from app.db.session import session_factory
from app.models import Country, WorkflowStage, WorkflowStageDocumentRequirement, WorkflowTemplate
from app.models.enums import DocumentType


@dataclass
class StageSpec:
    key: str
    name: str
    category: str
    color: str
    icon: str
    description: str = ""
    requirements: list[tuple[DocumentType | None, str | None, bool]] = field(default_factory=list)


# The base/default sequence, from the brief. Visa outcome is modeled via
# WorkflowStepStatus (completed vs failed) on "visa_approved" rather than a
# separate "visa_rejected" stage — a linear stage list can't represent two
# mutually-exclusive stages at the same position.
BASE_STAGES: list[StageSpec] = [
    StageSpec("lead_created", "Lead Created", "lead", "#6B7280", "UserPlus"),
    StageSpec("documents_requested", "Documents Requested", "documentation", "#3B82F6", "FileText"),
    StageSpec("documents_received", "Documents Received", "documentation", "#3B82F6", "Inbox"),
    StageSpec(
        "documents_verified",
        "Documents Verified",
        "documentation",
        "#10B981",
        "FileCheck",
        requirements=[
            (DocumentType.PASSPORT, None, True),
            (DocumentType.ACADEMIC_TRANSCRIPT, None, True),
            (DocumentType.ENGLISH_TEST, None, True),
            (DocumentType.STATEMENT_OF_PURPOSE, None, True),
            (DocumentType.RECOMMENDATION_LETTER, None, False),
        ],
    ),
    StageSpec("university_shortlisted", "University Shortlisted", "application", "#8B5CF6", "ListChecks"),
    StageSpec("university_applied", "University Applied", "application", "#8B5CF6", "Send"),
    StageSpec("application_submitted", "Application Submitted", "application", "#8B5CF6", "SendHorizontal"),
    StageSpec("under_review", "Under Review", "application", "#F59E0B", "Search"),
    StageSpec("interview_scheduled", "Interview Scheduled", "application", "#3B82F6", "CalendarClock"),
    StageSpec("interview_completed", "Interview Completed", "application", "#10B981", "CalendarCheck"),
    StageSpec(
        "offer_letter_received",
        "Offer Letter Received",
        "offer",
        "#10B981",
        "Award",
        requirements=[(DocumentType.OFFER_LETTER, None, True)],
    ),
    StageSpec("offer_accepted", "Offer Accepted", "offer", "#10B981", "CheckCircle2"),
    StageSpec(
        "tuition_fee_paid",
        "Tuition Fee Paid",
        "financial",
        "#10B981",
        "Wallet",
        requirements=[(DocumentType.FINANCIAL_DOCUMENT, None, True)],
    ),
    StageSpec(
        "cas_coe_issued",
        "CAS / COE Issued",
        "visa",
        "#F59E0B",
        "FileSignature",
        requirements=[(None, "CAS / COE Letter", True)],
    ),
    StageSpec(
        "visa_applied",
        "Visa Applied",
        "visa",
        "#F59E0B",
        "Plane",
        requirements=[(None, "Visa Application Form", True), (DocumentType.FINANCIAL_DOCUMENT, "Proof of funds", False)],
    ),
    StageSpec(
        "visa_approved",
        "Visa Approved",
        "visa",
        "#10B981",
        "PlaneTakeoff",
        requirements=[(DocumentType.VISA, None, True)],
    ),
    StageSpec("travel_preparation", "Travel Preparation", "travel", "#3B82F6", "Luggage"),
    StageSpec("departure", "Departure", "travel", "#3B82F6", "PlaneTakeoff"),
    StageSpec("arrived", "Arrived", "travel", "#10B981", "MapPin"),
    StageSpec("case_completed", "Case Completed", "completion", "#10B981", "PartyPopper"),
]

COUNTRIES = {
    "AU": {"name": "Australia", "iso3": "AUS", "phone_code": "+61", "currency_code": "AUD"},
    "CA": {"name": "Canada", "iso3": "CAN", "phone_code": "+1", "currency_code": "CAD"},
    "GB": {"name": "United Kingdom", "iso3": "GBR", "phone_code": "+44", "currency_code": "GBP"},
    "US": {"name": "United States", "iso3": "USA", "phone_code": "+1", "currency_code": "USD"},
}


def build_country_stages(country_iso2: str) -> list[StageSpec]:
    """Clone BASE_STAGES and splice in each country's real-world visa steps."""
    stages = [StageSpec(**{**s.__dict__, "requirements": list(s.requirements)}) for s in BASE_STAGES]
    by_key = {s.key: i for i, s in enumerate(stages)}

    if country_iso2 == "AU":
        stages[by_key["cas_coe_issued"]] = StageSpec(
            "coe_issued", "COE Issued", "visa", "#F59E0B", "FileSignature", requirements=[(None, "Confirmation of Enrolment (COE)", True)]
        )
        stages[by_key["visa_applied"]] = StageSpec(
            "visa_lodgement", "Visa Lodgement", "visa", "#F59E0B", "Plane", requirements=[(None, "Visa Lodgement Receipt", True)]
        )
        stages[by_key["visa_approved"]] = StageSpec(
            "visa_granted", "Visa Granted", "visa", "#10B981", "PlaneTakeoff", requirements=[(DocumentType.VISA, None, True)]
        )
        stages.insert(
            by_key["tuition_fee_paid"] + 1,
            StageSpec("genuine_student_assessment", "Genuine Student Assessment", "visa", "#F59E0B", "ShieldCheck"),
        )

    elif country_iso2 == "CA":
        stages[by_key["offer_letter_received"]] = StageSpec(
            "loa_received", "LOA Received", "offer", "#10B981", "Award", requirements=[(None, "Letter of Acceptance (LOA)", True)]
        )
        stages[by_key["tuition_fee_paid"]] = StageSpec(
            "tuition_deposit_paid", "Tuition Deposit Paid", "financial", "#10B981", "Wallet", requirements=[(DocumentType.FINANCIAL_DOCUMENT, None, True)]
        )
        stages[by_key["visa_applied"]] = StageSpec(
            "study_permit_applied", "Study Permit Applied", "visa", "#F59E0B", "Plane", requirements=[(None, "Study Permit Application", True)]
        )
        stages[by_key["visa_approved"]] = StageSpec(
            "study_permit_approved", "Study Permit Approved", "visa", "#10B981", "PlaneTakeoff", requirements=[(DocumentType.VISA, None, True)]
        )
        del stages[by_key["cas_coe_issued"]]
        stages.insert(
            by_key["visa_applied"] - 1,
            StageSpec("pal_received", "PAL Received", "visa", "#F59E0B", "ShieldCheck", requirements=[(None, "Provincial Attestation Letter (PAL)", True)]),
        )

    elif country_iso2 == "GB":
        stages[by_key["cas_coe_issued"]] = StageSpec(
            "cas_issued", "CAS Issued", "visa", "#F59E0B", "FileSignature", requirements=[(None, "Confirmation of Acceptance for Studies (CAS)", True)]
        )
        stages.insert(by_key["visa_applied"], StageSpec("tb_test_completed", "TB Test Completed", "visa", "#3B82F6", "Stethoscope", requirements=[(DocumentType.MEDICAL_REPORT, None, True)]))
        stages.insert(by_key["visa_applied"] + 1, StageSpec("visa_biometrics", "Visa Biometrics", "visa", "#3B82F6", "Fingerprint"))

    elif country_iso2 == "US":
        stages[by_key["cas_coe_issued"]] = StageSpec(
            "i20_issued", "I-20 Issued", "visa", "#F59E0B", "FileSignature", requirements=[(None, "Form I-20", True)]
        )
        stages[by_key["visa_applied"]] = StageSpec(
            "ds160_submitted", "DS-160 Submitted", "visa", "#F59E0B", "Plane", requirements=[(None, "DS-160 Confirmation", True)]
        )
        stages.insert(by_key["visa_applied"], StageSpec("sevis_fee_paid", "SEVIS Fee Paid", "financial", "#10B981", "Wallet", requirements=[(None, "SEVIS Fee Receipt", True)]))
        stages.insert(by_key["visa_approved"], StageSpec("visa_interview_scheduled", "Visa Interview Scheduled", "visa", "#3B82F6", "CalendarClock"))

    return stages


async def upsert_country(session, iso2: str, data: dict) -> Country:
    result = await session.execute(select(Country).where(Country.iso2 == iso2))
    country = result.scalar_one_or_none()
    if country is None:
        country = Country(iso2=iso2, **data)
        session.add(country)
        await session.flush()
    return country


async def upsert_template(session, *, name: str, slug: str, description: str, country_id, is_default: bool, stages: list[StageSpec]) -> None:
    result = await session.execute(select(WorkflowTemplate).where(WorkflowTemplate.slug == slug))
    if result.scalar_one_or_none() is not None:
        print(f"skip (exists): {slug}")
        return

    template = WorkflowTemplate(name=name, slug=slug, description=description, country_id=country_id, is_default=is_default)
    session.add(template)
    await session.flush()

    for order, spec in enumerate(stages):
        stage = WorkflowStage(
            template_id=template.id,
            key=spec.key,
            name=spec.name,
            description=spec.description,
            category=spec.category,
            color=spec.color,
            icon=spec.icon,
            order=order,
        )
        session.add(stage)
        await session.flush()
        for document_type, custom_label, is_required in spec.requirements:
            session.add(
                WorkflowStageDocumentRequirement(
                    stage_id=stage.id,
                    document_type=document_type,
                    custom_label=custom_label,
                    is_required=is_required,
                )
            )

    await session.commit()
    print(f"created: {slug} ({len(stages)} stages)")


async def main() -> None:
    async with session_factory() as session:
        await upsert_template(
            session,
            name="Default",
            slug="default",
            description="Generic admission journey used when no country-specific template applies.",
            country_id=None,
            is_default=True,
            stages=BASE_STAGES,
        )

        for iso2, data in COUNTRIES.items():
            country = await upsert_country(session, iso2, data)
            await upsert_template(
                session,
                name=f"{data['name']} Workflow",
                slug=f"{iso2.lower()}-workflow",
                description=f"Admission and visa journey for {data['name']}-bound applicants.",
                country_id=country.id,
                is_default=False,
                stages=build_country_stages(iso2),
            )


if __name__ == "__main__":
    asyncio.run(main())
