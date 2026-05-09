from enum import Enum


class Role(str, Enum):
    student = "student"
    company = "company"
    admin = "admin"


class Branch(str, Enum):
    CSE = "CSE"
    ECE = "ECE"
    EE = "EE"
    ME = "ME"
    CE = "CE"
    MME = "MME"
    CHE = "CHE"


class Gender(str, Enum):
    male = "male"
    female = "female"
    other = "other"


class RoleType(str, Enum):
    full_time = "full_time"
    internship = "internship"


class ApplicationStatus(str, Enum):
    applied = "applied"
    shortlisted = "shortlisted"
    rejected = "rejected"
    offered = "offered"
    accepted = "accepted"
    declined = "declined"
    offer_expired = "offer_expired"
    closed_by_job = "closed_by_job"
    inactive_student = "inactive_student"


class ApplicationStatusReason(str, Enum):
    """Why an application changed status"""
    initial = "initial"
    manual_rejection = "manual_rejection"
    manual_shortlist = "manual_shortlist"
    manual_offer = "manual_offer"
    offer_accepted = "offer_accepted"
    offer_declined = "offer_declined"
    offer_deadline_expired = "offer_deadline_expired"
    job_closed = "job_closed"
    student_deactivated = "student_deactivated"


class OfferStatus(str, Enum):
    offered = "offered"
    accepted = "accepted"
    declined = "declined"
    invalidated = "invalidated"


class OfferStatusReason(str, Enum):
    """Why an offer changed status"""
    initial = "initial"
    offer_accepted = "offer_accepted"
    offer_declined = "offer_declined"
    competing_offer_accepted = "competing_offer_accepted"
    job_closed = "job_closed"
    student_deactivated = "student_deactivated"
    deadline_passed = "deadline_passed"


class CompanyApplicationAction(str, Enum):
    shortlisted = "shortlisted"
    rejected = "rejected"
    offered = "offered"
