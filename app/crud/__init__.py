"""
CRUD operations for the Placement Portal.

This module aggregates all CRUD operations from submodules:
- user_crud: User authentication and management
- student_crud: Student profile management
- company_crud: Company profile management
- job_crud: Job postings management
- application_crud: Job applications management
- offer_crud: Job offers management
"""

from .user_crud import (
    create_user,
    authenticate_user,
    get_user_by_id,
    get_user_by_email,
    get_all_users,
    count_users,
    verify_admin,
    update_user_verification,
    update_user_password,
    get_pending_admins,
    count_pending_admins,
    purge_expired_unverified_users,
)

from .student_crud import (
    create_student,
    get_student_by_user_id,
    get_student_by_id,
    update_student,
    delete_student,
    reactivate_student,
    list_students,
    count_students,
    count_placed_students,
)

from .company_crud import (
    create_company,
    get_company_by_user_id,
    get_company_by_id,
    update_company,
    delete_company,
    reactivate_company,
    list_companies,
    count_companies,
    verify_company,
)

from .job_crud import (
    create_job,
    get_job_by_id,
    list_jobs,
    count_jobs,
    count_active_jobs,
    count_verified_jobs,
    list_verified_jobs,
    get_applicants_for_job,
    close_job,
    delete_job,
)

from .application_crud import (
    apply_job,
    get_application_by_id,
    withdraw_application,
    shortlist_applicant,
    reject_applicant,
    list_applications,
    count_applications,
    delete_application,
    update_application_status,
    apply_company_action,
)

from .offer_crud import (
    create_offer,
    accept_offer,
    decline_offer,
    get_offers_for_student,
    count_offers_made,
    count_offers_accepted,
)

# Alias for backwards compatibility
get_verified_jobs = list_verified_jobs

__all__ = [
    # User
    "create_user",
    "authenticate_user",
    "get_user_by_id",
    "get_user_by_email",
    "get_all_users",
    "count_users",
    "verify_admin",
    "update_user_verification",
    "update_user_password",
    "get_pending_admins",
    "count_pending_admins",
    "purge_expired_unverified_users",
    # Student
    "create_student",
    "get_student_by_user_id",
    "get_student_by_id",
    "update_student",
    "delete_student",
    "reactivate_student",
    "list_students",
    "count_students",
    "count_placed_students",
    # Company
    "create_company",
    "get_company_by_user_id",
    "get_company_by_id",
    "update_company",
    "delete_company",
    "reactivate_company",
    "list_companies",
    "count_companies",
    "verify_company",
    # Job
    "create_job",
    "get_job_by_id",
    "list_jobs",
    "count_jobs",
    "count_active_jobs",
    "count_verified_jobs",
    "list_verified_jobs",
    "get_applicants_for_job",
    "close_job",
    "delete_job",
    # Application
    "apply_job",
    "get_application_by_id",
    "withdraw_application",
    "shortlist_applicant",
    "reject_applicant",
    "list_applications",
    "count_applications",
    "delete_application",
    "update_application_status",
    "apply_company_action",
    # Offer
    "create_offer",
    "accept_offer",
    "decline_offer",
    "get_offers_for_student",
    "count_offers_made",
    "count_offers_accepted",
]

