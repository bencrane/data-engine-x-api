"""
HQ Master Data Ingest - Modal App Entry Point

This is the ONLY file that should be deployed. It imports all modules
and exposes all endpoints for the hq-master-data-ingest app.

Deploy command (from modal-mcp-server/ directory, using uv):
    cd /Users/benjamincrane/hq-master-data-warehouse-v2/modal-mcp-server
    uv run modal deploy src/app.py

IMPORTANT: Do NOT run `modal deploy` directly - use `uv run` to ensure
dependencies (pydantic, etc.) are available from the uv-managed venv.

Rules:
    1. All code must be committed to main before deploy
    2. Always deploy from this entry point
    3. Always deploy from main branch
    4. Always use `uv run modal deploy` (not bare `modal deploy`)
"""

# Import the app from config (this is what Modal looks for)
import modal
from config import app, image

# Import all endpoint modules - this registers them with the app
# These imports must happen AFTER app is defined in config
# Import endpoints
from read.db_check import read_db_check_existence
from read.lookup_company_description import lookup_company_description
from read.lookup_company_firmographics import lookup_company_firmographics
from read.lookup_company_business_model import lookup_company_business_model
from read.lookup_similar_companies import lookup_similar_companies
from read.lookup_similar_companies_list import lookup_similar_companies_list
from read.lookup_client_leads import lookup_client_leads
from read.lookup_company_canonical import lookup_company_canonical
from ingest.company import ingest_clay_company_firmo, ingest_clay_find_companies, ingest_all_comp_customers, upsert_core_company, ingest_manual_comp_customer, ingest_clay_find_co_lctn_prsd
from ingest.person import ingest_clay_person_profile, ingest_clay_find_people, ingest_clay_find_ppl_lctn_prsd, ingest_ppl_title_enrich
from ingest.clay_native_person import ingest_clay_native_person, ingest_clay_native_person_batch
from ingest.case_study import ingest_case_study_extraction
from ingest.case_study_buyer import extract_case_study_buyer
from ingest.case_study_champions import ingest_case_study_buyers
from ingest.waterfall import command_center_email_enrichment, get_email_job
from ingest.icp_verdict import ingest_icp_verdict
from ingest.crunchbase_domain import infer_crunchbase_domain
from ingest.signal_new_hire import ingest_clay_signal_new_hire
from ingest.signal_news_fundraising import ingest_clay_signal_news_fundraising
from ingest.signal_job_posting import ingest_clay_signal_job_posting
from ingest.signal_job_change import ingest_clay_signal_job_change
from ingest.signal_promotion import ingest_clay_signal_promotion
from ingest.signal_job_posting_v2 import ingest_signal_job_posting
from ingest.signal_job_change_v2 import ingest_signal_job_change
from ingest.signal_promotion_v2 import ingest_signal_promotion
from ingest.company_address import ingest_company_address_parsing
from ingest.lookup import lookup_person_location, lookup_salesnav_location, lookup_salesnav_company_location, lookup_job_title, ingest_clay_company_location_lookup, ingest_clay_person_location_lookup
from ingest.lookup_company_name import lookup_company_name
from ingest.lookup_company_icp import lookup_company_icp
from ingest.lookup_company_customers import lookup_company_customers
from ingest.lookup_case_study_details import lookup_case_study_details
from ingest.lookup_case_study_champions import lookup_case_study_champions
from ingest.lookup_case_study_champions_detailed import lookup_champions_detailed
from ingest.lookup_alumni import lookup_alumni
from ingest.create_target_client_view import create_target_client_view
from ingest.upsert_icp_criteria import upsert_icp_criteria
from ingest.vc_portfolio import ingest_vc_portfolio
from ingest.vc_investors import ingest_company_vc_investors
from ingest.backfill import backfill_person_location, backfill_person_matched_location
from ingest.backfill_cleaned_company_name import backfill_cleaned_company_name
from ingest.backfill_company_descriptions import backfill_company_descriptions
from ingest.backfill_parallel_to_core import backfill_parallel_to_core
from ingest.generate_icp_title_patterns import generate_icp_title_patterns
from ingest.salesnav_person import ingest_salesnav_person
from ingest.salesnav_person_full import ingest_salesnav_person_full
from ingest.salesnav_clay_ingest import ingest_salesnav_clay
from ingest.salesnav_clay_basic import ingest_salesnav_clay_basic
from ingest.nostra_ecom import ingest_nostra_ecom_company
from ingest.nostra_ecom_people import ingest_nostra_ecom_person
from ingest.leadmagic_company import ingest_leadmagic_company
from ingest.companyenrich import ingest_companyenrich
from ingest.core_company_simple import ingest_core_company_simple
from ingest.apollo_scrape import ingest_apollo_scrape
from ingest.cleaned_company_name import ingest_cleaned_company_name
from ingest.salesnav_company import ingest_salesnav_company
from ingest.apollo_instantdata import extract_apollo_instantdata
from ingest.apollo_people_cleaned import ingest_apollo_people_cleaned
from ingest.apollo_companies_cleaned import ingest_apollo_companies_cleaned
from ingest.company_enrich_similar import find_similar_companies_batch, find_similar_companies_single, get_similar_companies_batch_status
from ingest.company_enrich_similar_queue import process_similar_companies_queue, get_similar_companies_queue_status
from ingest.companyenrich_similar_companies_preview_results import ingest_companyenrich_similar_preview_results
from ingest.send_client_leads_to_clay import send_client_leads_to_clay
from ingest.focus_company import ingest_focus_company
from ingest.company_customers_claygent import ingest_company_customers_claygent
from ingest.company_customers_structured import ingest_company_customers_structured
from ingest.send_case_study_urls import send_case_study_urls_to_clay
from ingest.send_unresolved_customers_to_clay import send_unresolved_customers_to_clay
from ingest.resolve_customer_domain import resolve_customer_domain
from ingest.company_customers_v2 import ingest_company_customers_v2
from ingest.company_customers_status import get_company_customers_status
from ingest.company_public import ingest_public_company
from ingest.company_ticker import ingest_company_ticker
from ingest.sec_financials import ingest_sec_financials
from ingest.sec_filings import fetch_sec_filings
from ingest.sec_filing_analysis import analyze_sec_10k, analyze_sec_10q, analyze_sec_8k_executive
from ingest.vc_domain_lookup import lookup_vc_domain
from ingest.vc_domain_update import update_vc_domain
from ingest.has_raised_vc import has_raised_vc
from ingest.cb_vc_portfolio import ingest_cb_vc_portfolio
from ingest.staging_company_enrich import update_staging_company_linkedin
from ingest.industry_inference import infer_company_industry
from ingest.country_inference import infer_company_country
from ingest.employee_range_inference import infer_company_employee_range
from ingest.core_company_full import upsert_core_company_full
from ingest.linkedin_url_inference import infer_company_linkedin_url
from ingest.meta_description import fetch_meta_description
from ingest.email_anymailfinder import ingest_email_anymailfinder
from ingest.email_leadmagic import ingest_email_leadmagic
from ingest.email_icypeas import ingest_email_icypeas
from ingest.icp_industries import ingest_icp_industries
from ingest.icp_job_titles import ingest_icp_job_titles
from ingest.icp_value_proposition import ingest_icp_value_proposition
from ingest.icp_fit_criterion import ingest_icp_fit_criterion
from ingest.builtwith import ingest_builtwith
from ingest.predictleads_techstack import ingest_predictleads_techstack
from ingest.job_posting import ingest_job_posting
from ingest.company_classification import ingest_company_classification
from ingest.linkedin_ads import ingest_linkedin_ads
from ingest.google_ads import ingest_google_ads
from ingest.meta_ads import ingest_meta_ads
from ingest.sales_motion import infer_sales_motion
from ingest.free_trial import infer_free_trial
from ingest.pricing_visibility import infer_pricing_visibility
from ingest.pricing_model import infer_pricing_model
from ingest.billing_default import infer_billing_default
from ingest.number_of_tiers import infer_number_of_tiers
from ingest.add_ons_offered import infer_add_ons_offered
from ingest.enterprise_tier_exists import infer_enterprise_tier_exists
from ingest.security_compliance_gating import infer_security_gating
from ingest.annual_commitment_required import infer_annual_commitment
from ingest.plan_naming_style import infer_plan_naming_style
from ingest.custom_pricing_mentioned import infer_custom_pricing_mentioned
from ingest.money_back_guarantee import infer_money_back_guarantee
from ingest.comparison_page_exists import infer_comparison_page_exists
from ingest.minimum_seats import infer_minimum_seats
from ingest.webinars import infer_webinars
from ingest.discover_pricing_page import discover_pricing_page_url
from ingest.discover_g2_page import discover_g2_page_gemini
from ingest.discover_g2_page_search import discover_g2_page_gemini_search
from ingest.discover_competitors import discover_competitors_openai
from ingest.ingest_competitors import ingest_competitors
from ingest.g2_page_scrape import ingest_g2_page_scrape_zenrows
from ingest.scrape_g2_reviews import scrape_g2_reviews
from ingest.parallel_search import search_parallel_ai
from ingest.parallel_task_enrichment import infer_parallel_hq_location, infer_parallel_industry, infer_parallel_competitors
from ingest.staffing_parallel_search import ingest_staffing_parallel_search
from ingest.attio_job_postings import sync_job_postings_to_attio
from ingest.company_canonical import ingest_company_canonical
from ingest.parallel_case_study import ingest_parallel_case_study
from ingest.validate_company_name import validate_company_name
from ingest.infer_customer_domain import infer_customer_domain
from ingest.ingest_gemini_domain_inference import ingest_gemini_domain_inference
from ingest.resolve_orphan_customer_domain import resolve_orphan_customer_domain
from ingest.ingest_company_description import ingest_company_description
from ingest.ingest_orphan_customer_domain import ingest_orphan_customer_domain
from ingest.validate_export_title import validate_export_title
from ingest.brightdata_indeed_jobs import ingest_brightdata_indeed_jobs
from ingest.brightdata_linkedin_jobs import ingest_brightdata_linkedin_jobs
from icp.generation import generate_target_client_icp
from cleanup.delete_companies_no_location import delete_companies_no_location

# CRITICAL: Explicitly import extraction module so Modal mounts it.
# The ingest functions import from extraction.company and extraction.person
# inside their function bodies (lazy imports). Modal's static analysis may
# not detect these runtime imports, so we force it to mount the package here.
import extraction.company
import extraction.person
import extraction.case_study
import extraction.case_study_champions
import extraction.icp_verdict
import extraction.crunchbase_domain
import extraction.signal_new_hire
import extraction.signal_news_fundraising
import extraction.signal_job_posting
import extraction.signal_job_change
import extraction.signal_promotion
import extraction.signal_job_posting_v2
import extraction.signal_job_change_v2
import extraction.signal_promotion_v2
import extraction.company_address
import extraction.salesnav_person
import extraction.salesnav_clay
import extraction.vc_investors
import extraction.company_mapping
import extraction.person_mapping
import extraction.cb_vc_portfolio
import extraction.email_anymailfinder
import extraction.email_leadmagic
import extraction.icp_industries
import extraction.icp_job_titles
import extraction.icp_value_proposition
import extraction.icp_fit_criterion

# Import prompts module so Modal mounts it
import prompts.sec_filings

# Simple test endpoint - always keep this
@app.function(image=image)
@modal.fastapi_endpoint(method="POST")
def test_endpoint(data: dict) -> dict:
    """Simple test endpoint that echoes back what you send."""
    return {"success": True, "received": data}


# Re-export for clarity
__all__ = [
    "app",
    "image",
    "test_endpoint",
    "ingest_clay_find_ppl_lctn_prsd",
    "ingest_ppl_title_enrich",
    "ingest_clay_company_firmo",
    "ingest_clay_find_companies",
    "ingest_clay_find_co_lctn_prsd",
    "ingest_all_comp_customers",
    "upsert_core_company",
    "ingest_manual_comp_customer",
    "ingest_clay_person_profile",
    "ingest_clay_find_people",
    "ingest_clay_native_person",
    "ingest_clay_native_person_batch",
    "ingest_case_study_extraction",
    "extract_case_study_buyer",
    "ingest_case_study_buyers",
    "ingest_icp_verdict",
    "generate_target_client_icp",
    "command_center_email_enrichment",
    "get_email_job",
    "infer_crunchbase_domain",
    "ingest_clay_signal_new_hire",
    "ingest_clay_signal_news_fundraising",
    "ingest_clay_signal_job_posting",
    "ingest_clay_signal_job_change",
    "ingest_clay_signal_promotion",
    "ingest_signal_job_posting",
    "ingest_signal_job_change",
    "ingest_signal_promotion",
    "ingest_company_address_parsing",
    "lookup_person_location",
    "lookup_salesnav_location",
    "lookup_salesnav_company_location",
    "lookup_job_title",
    "ingest_clay_company_location_lookup",
    "ingest_clay_person_location_lookup",
    "ingest_vc_portfolio",
    "ingest_company_vc_investors",
    "backfill_person_location",
    "backfill_person_matched_location",
    "ingest_salesnav_person",
    "ingest_salesnav_person_full",
    "ingest_salesnav_clay",
    "ingest_salesnav_clay_basic",
    "ingest_nostra_ecom_company",
    "ingest_nostra_ecom_person",
    "ingest_leadmagic_company",
    "ingest_companyenrich",
    "ingest_core_company_simple",
    "ingest_apollo_scrape",
    "ingest_cleaned_company_name",
    "ingest_salesnav_company",
    "extract_apollo_instantdata",
    "backfill_cleaned_company_name",
    "backfill_company_descriptions",
    "ingest_apollo_people_cleaned",
    "ingest_apollo_companies_cleaned",
    "find_similar_companies_batch",
    "find_similar_companies_single",
    "get_similar_companies_batch_status",
    "process_similar_companies_queue",
    "get_similar_companies_queue_status",
    "ingest_company_customers_claygent",
    "ingest_company_customers_structured",
    "ingest_company_customers_v2",
    "get_company_customers_status",
    "ingest_public_company",
    "ingest_company_ticker",
    "ingest_sec_financials",
    "fetch_sec_filings",
    "analyze_sec_10k",
    "analyze_sec_10q",
    "analyze_sec_8k_executive",
    "lookup_vc_domain",
    "update_vc_domain",
    "has_raised_vc",
    "ingest_cb_vc_portfolio",
    "update_staging_company_linkedin",
    "infer_company_industry",
    "infer_company_country",
    "infer_company_employee_range",
    "upsert_core_company_full",
    "infer_company_linkedin_url",
    "fetch_meta_description",
    "ingest_email_anymailfinder",
    "ingest_email_leadmagic",
    "ingest_icp_industries",
    "ingest_icp_job_titles",
    "ingest_icp_value_proposition",
    "ingest_icp_fit_criterion",
    "ingest_builtwith",
    "ingest_predictleads_techstack",
    "ingest_job_posting",
    "ingest_company_classification",
    "ingest_linkedin_ads",
    "ingest_google_ads",
    "ingest_meta_ads",
    "infer_sales_motion",
    "infer_free_trial",
    "infer_pricing_visibility",
    "infer_pricing_model",
    "infer_billing_default",
    "infer_number_of_tiers",
    "infer_add_ons_offered",
    "infer_enterprise_tier_exists",
    "infer_security_gating",
    "infer_annual_commitment",
    "infer_plan_naming_style",
    "infer_custom_pricing_mentioned",
    "infer_money_back_guarantee",
    "infer_comparison_page_exists",
    "infer_minimum_seats",
    "infer_webinars",
    "discover_pricing_page_url",
    "discover_g2_page_gemini",
    "discover_g2_page_gemini_search",
    "discover_competitors_openai",
    "ingest_competitors",
    "ingest_g2_page_scrape_zenrows",
    "search_parallel_ai",
    "infer_parallel_hq_location",
    "infer_parallel_industry",
    "infer_parallel_competitors",
    "ingest_staffing_parallel_search",
    "read_db_check_existence",
    "lookup_company_description",
    "lookup_company_business_model",
    "lookup_similar_companies",
    "lookup_similar_companies_list",
    "send_case_study_urls_to_clay",
    "lookup_case_study_details",
    "send_unresolved_customers_to_clay",
    "resolve_customer_domain",
    "resolve_orphan_customer_domain",
    "ingest_company_description",
    "ingest_orphan_customer_domain",
    "ingest_companyenrich_similar_preview_results",
    "lookup_client_leads",
    "send_client_leads_to_clay",
    "ingest_focus_company",
    "lookup_alumni",
    "validate_export_title",
    "ingest_brightdata_indeed_jobs",
    "ingest_brightdata_linkedin_jobs",
]
