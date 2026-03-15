"""
Cross-provider synonym tables for enum resolution.

Each table maps a lowercase alias to the exact provider-specific enum value.
These handle cases where the same concept has different names across providers
(e.g. "VP" in BlitzAPI vs "Vice President" in Prospeo) or where common
shorthand needs to resolve to a specific value.
"""

# ---------------------------------------------------------------------------
# Seniority synonyms
# ---------------------------------------------------------------------------

PROSPEO_SENIORITY_SYNONYMS: dict[str, str] = {
    "vp": "Vice President",
    "vice president": "Vice President",
    "c-suite": "C-Suite",
    "c-team": "C-Suite",
    "csuite": "C-Suite",
    "cxo": "C-Suite",
    "ceo": "C-Suite",
    "cfo": "C-Suite",
    "cto": "C-Suite",
    "coo": "C-Suite",
    "cro": "C-Suite",
    "cmo": "C-Suite",
    "founder": "Founder/Owner",
    "owner": "Founder/Owner",
    "co-founder": "Founder/Owner",
    "cofounder": "Founder/Owner",
    "head": "Head",
    "head of": "Head",
    "director": "Director",
    "manager": "Manager",
    "senior": "Senior",
    "entry": "Entry",
    "entry level": "Entry",
    "junior": "Entry",
    "intern": "Intern",
    "internship": "Intern",
    "partner": "Partner",
    "staff": "Senior",
}

BLITZAPI_JOB_LEVEL_SYNONYMS: dict[str, str] = {
    "c-suite": "C-Team",
    "csuite": "C-Team",
    "cxo": "C-Team",
    "ceo": "C-Team",
    "cfo": "C-Team",
    "cto": "C-Team",
    "coo": "C-Team",
    "cro": "C-Team",
    "cmo": "C-Team",
    "founder": "C-Team",
    "owner": "C-Team",
    "vice president": "VP",
    "vp": "VP",
    "head": "VP",
    "head of": "VP",
    "director": "Director",
    "director level": "Director",
    "manager": "Manager",
    "senior": "Staff",
    "entry": "Staff",
    "entry level": "Staff",
    "junior": "Staff",
    "intern": "Other",
    "individual contributor": "Staff",
    "ic": "Staff",
    "partner": "VP",
    "staff": "Staff",
    "other": "Other",
}

# ---------------------------------------------------------------------------
# Department / job function synonyms
# ---------------------------------------------------------------------------

PROSPEO_DEPARTMENT_SYNONYMS: dict[str, str] = {
    "sales": "All Sales",
    "marketing": "Advertising",
    "engineering": "Engineering & Technical",
    "hr": "All Human Resources",
    "human resources": "All Human Resources",
    "finance": "Accounting",
    "legal": "All Legal",
    "it": "Cloud Engineering",
    "information technology": "Cloud Engineering",
    "product": "All Product",
    "design": "All Design",
    "operations": "Supply Chain",
    "consulting": "Consultant",
    "medical": "Doctors / Physicians",
    "education": "Teacher",
    "customer service": "Customer Service / Support",
    "customer success": "Customer Success",
}

BLITZAPI_JOB_FUNCTION_SYNONYMS: dict[str, str] = {
    "sales": "Sales & Business Development",
    "marketing": "Advertising & Marketing",
    "engineering": "Engineering",
    "hr": "Human Resources",
    "human resources": "Human Resources",
    "finance": "Finance & Accounting",
    "legal": "Legal",
    "it": "Information Technology",
    "information technology": "Information Technology",
    "product": "General Business & Management",
    "operations": "Operations",
    "consulting": "General Business & Management",
    "medical": "Healthcare & Human Services",
    "healthcare": "Healthcare & Human Services",
    "education": "Education",
    "customer service": "Customer/Client Service",
    "construction": "Construction",
    "science": "Science",
    "r&d": "Research & Development",
    "research": "Research & Development",
    "supply chain": "Supply Chain & Logistics",
    "logistics": "Supply Chain & Logistics",
    "purchasing": "Purchasing",
    "writing": "Writing/Editing",
    "creative": "Art, Culture and Creative Professionals",
    "design": "Art, Culture and Creative Professionals",
    "manufacturing": "Manufacturing & Production",
    "government": "Public Administration & Safety",
}

# ---------------------------------------------------------------------------
# Employee range synonyms (handle tier mismatches between providers)
# ---------------------------------------------------------------------------

PROSPEO_EMPLOYEE_RANGE_SYNONYMS: dict[str, str] = {
    "1-50": "1-10",
    "11-50": "11-20",
    "51-200": "51-100",
    "1001-5000": "1001-2000",
    "10001+": "10000+",
    "small": "1-10",
    "medium": "201-500",
    "large": "5001-10000",
    "enterprise": "10000+",
}

BLITZAPI_EMPLOYEE_RANGE_SYNONYMS: dict[str, str] = {
    "11-20": "11-50",
    "21-50": "11-50",
    "51-100": "51-200",
    "101-200": "51-200",
    "1001-2000": "1001-5000",
    "2001-5000": "1001-5000",
    "10000+": "10001+",
    "small": "1-10",
    "medium": "201-500",
    "large": "5001-10000",
    "enterprise": "10001+",
}
