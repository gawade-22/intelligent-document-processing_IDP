"""
Multi-Class Document Classifier Service.
Automatically classifies documents into all 13 target domain categories:
1. Invoice
2. Purchase Order
3. Receipt
4. Bank Statement
5. Resume / CV
6. Certificate
7. Contract / Agreement
8. Delivery Challan
9. Medical Report
10. Insurance Document
11. ID Document
12. Expense Report
13. Application / Form
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DOCUMENT_TYPES = {
    "invoice": {
        "label": "Commercial Invoice",
        "description": "Commercial tax invoices, vendor bills, supplier accounts payable",
        "primary_fields": ["vendor_name", "invoice_number", "invoice_date", "items", "quantity", "tax_amount", "total_amount"],
        "field_labels": {
            "vendor_name": "Vendor Name",
            "invoice_number": "Invoice No.",
            "invoice_date": "Date",
            "items": "Items",
            "quantity": "Quantity",
            "tax_amount": "Tax",
            "total_amount": "Total Amount",
        },
    },
    "purchase_order": {
        "label": "Purchase Order",
        "description": "Procurement orders, PO confirmations, corporate buyer purchase orders",
        "primary_fields": ["po_number", "buyer_name", "supplier_name", "order_date", "items", "quantity", "unit_price", "total_amount"],
        "field_labels": {
            "po_number": "PO Number",
            "buyer_name": "Buyer",
            "supplier_name": "Supplier",
            "order_date": "Order Date",
            "items": "Items",
            "quantity": "Quantity",
            "unit_price": "Price",
            "total_amount": "Total",
        },
    },
    "receipt": {
        "label": "Store / Retail Receipt",
        "description": "Retail store, supermarket, restaurant, cafe, fuel, and merchant point-of-sale receipts",
        "primary_fields": ["store_name", "receipt_number", "receipt_date", "items", "subtotal_amount", "tax_amount", "payment_method", "total_amount"],
        "field_labels": {
            "store_name": "Store Name",
            "receipt_number": "Receipt No.",
            "receipt_date": "Date",
            "items": "Items",
            "subtotal_amount": "Amount",
            "tax_amount": "Tax",
            "payment_method": "Payment Method",
            "total_amount": "Total Amount",
        },
    },
    "bank_statement": {
        "label": "Bank Statement",
        "description": "Monthly bank account statements, ledger sheets, debit/credit transaction records",
        "primary_fields": ["account_holder", "account_number", "statement_period", "transaction_date", "transaction_description", "debit_amount", "credit_amount", "balance_amount"],
        "field_labels": {
            "account_holder": "Account Holder",
            "account_number": "Account No.",
            "statement_period": "Statement Period",
            "transaction_date": "Transaction Date",
            "transaction_description": "Description",
            "debit_amount": "Debit",
            "credit_amount": "Credit",
            "balance_amount": "Balance",
        },
    },
    "resume": {
        "label": "Resume / CV",
        "description": "Curriculum vitae, job applicant profiles, professional work experience",
        "primary_fields": ["candidate_name", "email", "phone", "skills", "education", "experience", "projects"],
        "field_labels": {
            "candidate_name": "Name",
            "email": "Email",
            "phone": "Phone",
            "skills": "Skills",
            "education": "Education",
            "experience": "Experience",
            "projects": "Projects",
        },
    },
    "certificate": {
        "label": "Certificate",
        "description": "Academic diplomas, training completion certificates, degrees, awards",
        "primary_fields": ["person_name", "certificate_type", "institution_name", "issue_date", "certificate_id"],
        "field_labels": {
            "person_name": "Person Name",
            "certificate_type": "Certificate Type",
            "institution_name": "Institution",
            "issue_date": "Issue Date",
            "certificate_id": "Certificate ID",
        },
    },
    "contract": {
        "label": "Contract / Agreement",
        "description": "Legal contracts, commercial agreements, non-disclosure agreements, service level terms",
        "primary_fields": ["parties", "agreement_date", "effective_date", "expiry_date", "contract_value", "terms_summary"],
        "field_labels": {
            "parties": "Parties",
            "agreement_date": "Agreement Date",
            "effective_date": "Effective Date",
            "expiry_date": "Expiry Date",
            "contract_value": "Contract Value",
            "terms_summary": "Terms",
        },
    },
    "delivery_challan": {
        "label": "Delivery Challan",
        "description": "Goods dispatch notes, delivery challans, consignment transport slips",
        "primary_fields": ["challan_number", "challan_date", "supplier_name", "customer_name", "items", "quantity", "transport_details"],
        "field_labels": {
            "challan_number": "Challan No.",
            "challan_date": "Date",
            "supplier_name": "Supplier",
            "customer_name": "Customer",
            "items": "Items",
            "quantity": "Quantity",
            "transport_details": "Transport Details",
        },
    },
    "medical_report": {
        "label": "Medical Report",
        "description": "Clinical lab reports, blood test results, pathology summaries, diagnostic findings",
        "primary_fields": ["patient_name", "report_date", "test_name", "test_result", "reference_range", "doctor_name"],
        "field_labels": {
            "patient_name": "Patient Name",
            "report_date": "Report Date",
            "test_name": "Test Name",
            "test_result": "Result",
            "reference_range": "Reference Range",
            "doctor_name": "Doctor",
        },
    },
    "insurance": {
        "label": "Insurance Document",
        "description": "Insurance policy schedules, health/motor/life cover details, premium schedules",
        "primary_fields": ["policy_number", "policy_holder", "insurance_type", "start_date", "expiry_date", "premium_amount"],
        "field_labels": {
            "policy_number": "Policy No.",
            "policy_holder": "Policy Holder",
            "insurance_type": "Insurance Type",
            "start_date": "Start Date",
            "expiry_date": "Expiry Date",
            "premium_amount": "Premium",
        },
    },
    "id_document": {
        "label": "ID Document",
        "description": "Passports, national ID cards, driver licenses, citizenship credentials",
        "primary_fields": ["person_name", "id_number", "date_of_birth", "address", "issue_expiry_date"],
        "field_labels": {
            "person_name": "Name",
            "id_number": "ID Number",
            "date_of_birth": "Date of Birth",
            "address": "Address",
            "issue_expiry_date": "Issue/Expiry Date",
        },
    },
    "expense_report": {
        "label": "Expense Report",
        "description": "Employee travel expense claims, reimbursement forms, corporate spend reports",
        "primary_fields": ["employee_name", "expense_date", "category", "description", "expense_amount", "total_amount"],
        "field_labels": {
            "employee_name": "Employee Name",
            "expense_date": "Expense Date",
            "category": "Category",
            "description": "Description",
            "expense_amount": "Amount",
            "total_amount": "Total",
        },
    },
    "application_form": {
        "label": "Application / Form",
        "description": "Admission applications, registration forms, survey forms, membership questionnaires",
        "primary_fields": ["applicant_name", "contact_details", "address", "application_number", "form_fields"],
        "field_labels": {
            "applicant_name": "Applicant Name",
            "contact_details": "Contact Details",
            "address": "Address",
            "application_number": "Application No.",
            "form_fields": "Form Fields",
        },
    },
    "general": {
        "label": "General Document",
        "description": "General business document or unspecified PDF",
        "primary_fields": ["vendor_name", "invoice_number", "invoice_date", "total_amount"],
        "field_labels": {
            "vendor_name": "Vendor / Entity",
            "invoice_number": "Document ID #",
            "invoice_date": "Date",
            "total_amount": "Total / Value",
        },
    },
}

# Mapping aliases to canonical types
TYPE_ALIASES = {
    "bill": "invoice",
    "commercial_invoice": "invoice",
    "tax_invoice": "invoice",
    "po": "purchase_order",
    "retail_receipt": "receipt",
    "store_receipt": "receipt",
    "restaurant": "receipt",
    "travel": "receipt",
    "hotel": "receipt",
    "statement": "bank_statement",
    "bank_stmt": "bank_statement",
    "cv": "resume",
    "curriculum_vitae": "resume",
    "student_document": "certificate",
    "academic_record": "certificate",
    "marksheet": "certificate",
    "transcript": "certificate",
    "diploma": "certificate",
    "agreement": "contract",
    "nda": "contract",
    "mou": "contract",
    "challan": "delivery_challan",
    "dispatch_slip": "delivery_challan",
    "lab_report": "medical_report",
    "health_report": "medical_report",
    "pathology_report": "medical_report",
    "insurance_policy": "insurance",
    "insurance_document": "insurance",
    "policy": "insurance",
    "id_card": "id_document",
    "passport": "id_document",
    "driver_license": "id_document",
    "driving_licence": "id_document",
    "national_id": "id_document",
    "expense_claim": "expense_report",
    "reimbursement": "expense_report",
    "application": "application_form",
    "form": "application_form",
}


class DocumentClassifier:
    """Classifies document content across all 13 domain categories."""

    DOCUMENT_TYPES = DOCUMENT_TYPES

    @classmethod
    def classify(
        cls,
        text: str,
        filename: str = "",
        user_hint: Optional[str] = None,
    ) -> Tuple[str, float]:
        """
        Classifies document text and filename into one of the 13 supported types.
        Returns:
            Tuple[str, float]: (classified_type, confidence_score)
        """
        if user_hint and user_hint.lower() != "auto":
            clean_hint = user_hint.lower().strip()
            canonical = TYPE_ALIASES.get(clean_hint, clean_hint)
            if canonical in DOCUMENT_TYPES:
                return canonical, 1.0

        combined = f"{filename} {text}".lower()

        scores: Dict[str, float] = {
            "invoice": 0.0,
            "purchase_order": 0.0,
            "receipt": 0.0,
            "bank_statement": 0.0,
            "resume": 0.0,
            "certificate": 0.0,
            "contract": 0.0,
            "delivery_challan": 0.0,
            "medical_report": 0.0,
            "insurance": 0.0,
            "id_document": 0.0,
            "expense_report": 0.0,
            "application_form": 0.0,
        }

        # 1. Purchase Order
        po_keywords = [
            r"\bpurchase\s*order\b", r"\bpo\s*(?:#|no|number|num)\b", r"\bbuyer\b", r"\bvendor\s*code\b",
            r"\brequisition\b", r"\bdeliver\s*to\b", r"\bship\s*to\b", r"\bpayment\s*terms\b",
            r"\borders?\s*placed\b", r"\bvendor\s*acceptance\b",
        ]
        for pat in po_keywords:
            matches = len(re.findall(pat, combined))
            scores["purchase_order"] += matches * 3.5

        # 2. Bank Statement
        bank_keywords = [
            r"\bbank\s*statement\b", r"\baccount\s*statement\b", r"\bstatement\s*of\s*account\b",
            r"\baccount\s*(?:#|no|number)\b", r"\baccount\s*holder\b", r"\bstatement\s*period\b",
            r"\bopening\s*balance\b", r"\bclosing\s*balance\b", r"\bavailable\s*balance\b",
            r"\bdebit(?:s)?\b", r"\bcredit(?:s)?\b", r"\bwithdrawal(?:s)?\b", r"\bdeposit(?:s)?\b",
            r"\bifsc\b", r"\biban\b", r"\bswift\s*code\b", r"\bbranch\b",
        ]
        for pat in bank_keywords:
            matches = len(re.findall(pat, combined))
            scores["bank_statement"] += matches * 3.5

        # 3. Resume / CV
        resume_keywords = [
            r"\bresume\b", r"\bcurriculum\s*vitae\b", r"\bcv\b", r"\bprofessional\s*summary\b",
            r"\bwork\s*experience\b", r"\bemployment\s*history\b", r"\beducation\b", r"\bskills\b",
            r"\btechnical\s*skills\b", r"\bprojects\b", r"\bcertifications\b", r"\bgithub\b", r"\blinkedin\b",
        ]
        for pat in resume_keywords:
            matches = len(re.findall(pat, combined))
            scores["resume"] += matches * 4.0

        # 4. Certificate
        cert_keywords = [
            r"\bcertificate\b", r"\bcertify\s*that\b", r"\bthis\s*is\s*to\s*certify\b",
            r"\bhas\s*successfully\s*completed\b", r"\bconferred\s*upon\b", r"\bawarded\s*to\b",
            r"\bdegree\s*of\b", r"\bdiploma\b", r"\bcompletion\b", r"\baccreditation\b",
            r"\bcertificate\s*id\b", r"\bmarksheet\b", r"\btranscript\b", r"\bgrade\s*card\b",
        ]
        for pat in cert_keywords:
            matches = len(re.findall(pat, combined))
            scores["certificate"] += matches * 4.0

        # 5. Contract / Agreement
        contract_keywords = [
            r"\bagreement\b", r"\bcontract\b", r"\bterms\s*and\s*conditions\b",
            r"\bwhereas\b", r"\bhereby\s*agree\b", r"\bparties\b", r"\beffective\s*date\b",
            r"\bexpiry\s*date\b", r"\btermination\b", r"\bgoverning\s*law\b",
            r"\bnon-disclosure\b", r"\bnda\b", r"\bindemnification\b", r"\bconfidentiality\b",
        ]
        for pat in contract_keywords:
            matches = len(re.findall(pat, combined))
            scores["contract"] += matches * 3.5

        # 6. Delivery Challan
        challan_keywords = [
            r"\bdelivery\s*challan\b", r"\bchallan\s*(?:#|no|number)\b", r"\bdispatch\s*slip\b",
            r"\bconsignment\s*note\b", r"\bvehicle\s*(?:#|no|number)\b", r"\blr\s*(?:#|no|number)\b",
            r"\btransporter\b", r"\bgoods\s*dispatched\b", r"\breceived\s*in\s*good\s*condition\b",
            r"\bconsignee\b", r"\bconsignor\b",
        ]
        for pat in challan_keywords:
            matches = len(re.findall(pat, combined))
            scores["delivery_challan"] += matches * 4.0

        # 7. Medical Report
        medical_keywords = [
            r"\bpatient\s*name\b", r"\bmedical\s*report\b", r"\blaboratory\s*report\b",
            r"\bclinical\s*laboratory\b", r"\bdoctor\b", r"\bdr\.\s*[a-z]+\b", r"\bpathology\b",
            r"\bdiagnostic\b", r"\breference\s*range\b", r"\btest\s*name\b", r"\bresult\b",
            r"\bhaematology\b", r"\bbiochemistry\b", r"\burine\s*analysis\b", r"\bblood\s*test\b",
        ]
        for pat in medical_keywords:
            matches = len(re.findall(pat, combined))
            scores["medical_report"] += matches * 4.0

        # 8. Insurance Document
        insurance_keywords = [
            r"\binsurance\s*policy\b", r"\bpolicy\s*(?:#|no|number)\b", r"\bpolicy\s*holder\b",
            r"\bsum\s*insured\b", r"\bpremium\s*amount\b", r"\binsurance\s*type\b",
            r"\bcoverage\b", r"\bunderwriter\b", r"\binsurer\b", r"\bperiod\s*of\s*insurance\b",
            r"\bclaim\b", r"\bhealth\s*insurance\b", r"\bmotor\s*insurance\b",
        ]
        for pat in insurance_keywords:
            matches = len(re.findall(pat, combined))
            scores["insurance"] += matches * 3.5

        # 9. ID Document
        id_keywords = [
            r"\bidentity\s*card\b", r"\bdriver(?:'s)?\s*licen[sc]e\b", r"\bpassport\b",
            r"\bdate\s*of\s*birth\b", r"\bdob\b", r"\baadhaar\b", r"\bpan\s*card\b",
            r"\bvoter\s*id\b", r"\bssn\b", r"\bsocial\s*security\b", r"\bnational\s*id\b",
            r"\brepublic\s*of\b", r"\bgovernment\s*of\b", r"\bidentification\b",
        ]
        for pat in id_keywords:
            matches = len(re.findall(pat, combined))
            scores["id_document"] += matches * 4.0

        # 10. Expense Report
        expense_keywords = [
            r"\bexpense\s*report\b", r"\bexpense\s*claim\b", r"\bemployee\s*name\b",
            r"\bmileage\b", r"\breimbursement\b", r"\bper\s*diem\b", r"\btravel\s*expense\b",
            r"\bbusiness\s*purpose\b", r"\bexpense\s*date\b", r"\btotal\s*expenses\b",
        ]
        for pat in expense_keywords:
            matches = len(re.findall(pat, combined))
            scores["expense_report"] += matches * 4.0

        # 11. Application / Form
        app_keywords = [
            r"\bapplication\s*form\b", r"\badmission\s*form\b", r"\bapplicant\s*name\b",
            r"\bapplication\s*(?:#|no|number)\b", r"\bform\s*(?:#|no|number)\b", r"\bdeclaration\b",
            r"\bcontact\s*details\b", r"\bsignature\s*of\s*applicant\b", r"\benrollment\s*form\b",
        ]
        for pat in app_keywords:
            matches = len(re.findall(pat, combined))
            scores["application_form"] += matches * 3.5

        # 12. Retail / Store Receipt
        receipt_keywords = [
            r"\breceipt\b", r"\bstore\b", r"\bsupermarket\b", r"\bgrocery\b", r"\bmarket\b",
            r"\bpharmacy\b", r"\bwalmart\b", r"\btarget\b", r"\bcostco\b", r"\bstarbucks\b",
            r"\bregister\b", r"\bcashier\b", r"\bpos\b", r"\bitems\s*sold\b", r"\bchange\s*due\b",
            r"\bcash\s*tendered\b", r"\bbart\b", r"\bcaltrain\b", r"\bmetro\b", r"\btransit\b",
            r"\bdining\b", r"\brestaurant\b", r"\bcafe\b", r"\bhotel\b", r"\bfolio\b",
        ]
        for pat in receipt_keywords:
            matches = len(re.findall(pat, combined))
            scores["receipt"] += matches * 2.0

        # 13. Commercial Invoice
        invoice_keywords = [
            r"\btax\s*invoice\b", r"\bcommercial\s*invoice\b", r"\bproforma\s*invoice\b",
            r"\binvoice\s*(?:#|no|number|num)\b", r"\binv\s*#\b", r"\bbill\s*to\b",
            r"\binv[-_# ]\d+\b", r"\binvoice\b", r"\binv\b",
            r"\bgstin\b", r"\bvat\s*reg\b", r"\bdue\s*date\b", r"\bnet\s*payable\b",
            r"\bvendor\b", r"\btotal\s*amount\b", r"\bamount\s*due\b",
        ]
        for pat in invoice_keywords:
            matches = len(re.findall(pat, combined))
            scores["invoice"] += matches * 2.5

        # Filename hints
        if filename:
            fn_lower = filename.lower()
            if "invoice" in fn_lower or "inv_" in fn_lower or "_inv" in fn_lower:
                scores["invoice"] += 5.0
            elif "receipt" in fn_lower or "subway" in fn_lower or "ticket" in fn_lower:
                scores["receipt"] += 5.0
            elif "po" in fn_lower or "purchase_order" in fn_lower:
                scores["purchase_order"] += 5.0
            elif "resume" in fn_lower or "cv" in fn_lower:
                scores["resume"] += 5.0
            elif "bank" in fn_lower or "statement" in fn_lower:
                scores["bank_statement"] += 5.0
            elif "challan" in fn_lower:
                scores["delivery_challan"] += 5.0
            elif "medical" in fn_lower or "lab" in fn_lower:
                scores["medical_report"] += 5.0
            elif "certificate" in fn_lower or "marksheet" in fn_lower:
                scores["certificate"] += 5.0

        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        if best_score >= 3.0:
            confidence = min(0.98, round(0.60 + (best_score * 0.05), 2))
            logger.info(f"Classified document '{filename}' as {best_type} (score={best_score}, conf={confidence})")
            return best_type, confidence

        # Default fallback
        logger.info(f"Document '{filename}' low classifier signals, defaulting to 'invoice'")
        return "invoice", 0.50

    @classmethod
    def get_field_labels(cls, document_type: str) -> Dict[str, str]:
        """Returns human-readable field labels for a document type."""
        norm_type = TYPE_ALIASES.get((document_type or "invoice").lower(), (document_type or "invoice").lower())
        cfg = DOCUMENT_TYPES.get(norm_type, DOCUMENT_TYPES["invoice"])
        return cfg.get("field_labels", DOCUMENT_TYPES["invoice"]["field_labels"])

    @classmethod
    def get_display_name(cls, document_type: str) -> str:
        """Returns the human-readable display title for a document type."""
        norm_type = TYPE_ALIASES.get((document_type or "invoice").lower(), (document_type or "invoice").lower())
        cfg = DOCUMENT_TYPES.get(norm_type, DOCUMENT_TYPES["invoice"])
        return cfg.get("label", "Commercial Invoice")

    @classmethod
    def get_primary_fields(cls, document_type: str) -> List[str]:
        """Returns list of primary field names for a document type."""
        norm_type = TYPE_ALIASES.get((document_type or "invoice").lower(), (document_type or "invoice").lower())
        cfg = DOCUMENT_TYPES.get(norm_type, DOCUMENT_TYPES["invoice"])
        return cfg.get("primary_fields", DOCUMENT_TYPES["invoice"]["primary_fields"])


document_classifier = DocumentClassifier()
