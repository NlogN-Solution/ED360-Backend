from __future__ import annotations

import logging

logger = logging.getLogger("ignition.email")


def send_welcome_email(
    to_email: str,
    organization_name: str,
    temp_password: str,
    login_url: str,
) -> bool:
    """No SMTP/SES infra exists in this app — this logs the rendered email
    instead of sending it, the same "hand back credentials directly" approach
    already used by `reset_password`. A real provider implementation would
    replace the body of this function without changing its signature or callers.
    """
    logger.info(
        "Welcome email for %s (%s): temporary password=%s, login at %s",
        to_email,
        organization_name,
        temp_password,
        login_url,
    )
    return True
