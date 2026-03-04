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


class OfferStatus(str, Enum):
    offered = "offered"
    accepted = "accepted"
    declined = "declined"