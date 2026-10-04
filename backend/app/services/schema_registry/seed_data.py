"""
Seed Data for Dynamic IDP Schema Registry.
Converts the legacy 13 document types and canonical key aliases into persistent
database records, fulfilling the principle that knowledge is data, not code.
"""

from typing import Any, Dict, List

# -----------------------------------------------------------------------------
# 1. Canonical Key Aliases
# -----------------------------------------------------------------------------
SEED_CANONICAL_ALIASES: List[Dict[str, str]] = [
    # Person / Identity
    {"canonical_key": "person.full_name", "alias": "candidate_name", "data_type": "string", "family": "employment"},
    {"canonical_key": "person.full_name", "alias": "applicant_name", "data_type": "string", "family": "employment"},
    {"canonical_key": "person.full_name", "alias": "student_name", "data_type": "string", "family": "academic"},
    {"canonical_key": "person.full_name", "alias": "patient_name", "data_type": "string", "family": "medical"},
    {"canonical_key": "person.full_name", "alias": "full_name", "data_type": "string", "family": "identity"},
    {"canonical_key": "person.email", "alias": "email", "data_type": "email", "family": "general"},
    {"canonical_key": "person.phone", "alias": "phone", "data_type": "phone", "family": "general"},
    {"canonical_key": "person.phone", "alias": "contact_number", "data_type": "phone", "family": "general"},

    # Entity / Vendor
    {"canonical_key": "entity.vendor_name", "alias": "vendor_name", "data_type": "string", "family": "financial"},
    {"canonical_key": "entity.vendor_name", "alias": "supplier_name", "data_type": "string", "family": "financial"},
    {"canonical_key": "entity.vendor_name", "alias": "store_name", "data_type": "string", "family": "financial"},
    {"canonical_key": "entity.vendor_name", "alias": "merchant_name", "data_type": "string", "family": "financial"},
    {"canonical_key": "entity.vendor_name", "alias": "buyer_name", "data_type": "string", "family": "financial"},

    # Document Reference & Dates
    {"canonical_key": "document.reference_number", "alias": "invoice_number", "data_type": "id", "family": "financial"},
    {"canonical_key": "document.reference_number", "alias": "receipt_number", "data_type": "id", "family": "financial"},
    {"canonical_key": "document.reference_number", "alias": "po_number", "data_type": "id", "family": "financial"},
    {"canonical_key": "document.reference_number", "alias": "challan_number", "data_type": "id", "family": "logistics"},
    {"canonical_key": "document.date", "alias": "invoice_date", "data_type": "date", "family": "financial"},
    {"canonical_key": "document.date", "alias": "receipt_date", "data_type": "date", "family": "financial"},
    {"canonical_key": "document.date", "alias": "order_date", "data_type": "date", "family": "financial"},
    {"canonical_key": "document.date", "alias": "issue_date", "data_type": "date", "family": "general"},

    # Financial Amounts
    {"canonical_key": "financial.total_amount", "alias": "total_amount", "data_type": "money", "family": "financial"},
    {"canonical_key": "financial.total_amount", "alias": "grand_total", "data_type": "money", "family": "financial"},
    {"canonical_key": "financial.total_amount", "alias": "amount_due", "data_type": "money", "family": "financial"},
    {"canonical_key": "financial.tax_amount", "alias": "tax_amount", "data_type": "money", "family": "financial"},
    {"canonical_key": "financial.tax_amount", "alias": "gst_amount", "data_type": "money", "family": "financial"},
    {"canonical_key": "financial.tax_amount", "alias": "vat_amount", "data_type": "money", "family": "financial"},
    {"canonical_key": "financial.subtotal_amount", "alias": "subtotal_amount", "data_type": "money", "family": "financial"},

    # Banking
    {"canonical_key": "financial.account_number", "alias": "account_number", "data_type": "id", "family": "financial"},
    {"canonical_key": "person.account_holder", "alias": "account_holder", "data_type": "string", "family": "financial"},
    {"canonical_key": "financial.balance", "alias": "balance_amount", "data_type": "money", "family": "financial"},
]

# -----------------------------------------------------------------------------
# 2. Converted 13 Document Types (Initial Registry Templates)
# -----------------------------------------------------------------------------
SEED_SCHEMAS: List[Dict[str, Any]] = [
    {
        "id": "sch_commercial_invoice_v1",
        "name": "Commercial Invoice",
        "family": "financial",
        "version": 1,
        "origin": "template",
        "description": "Commercial tax invoices, vendor bills, supplier accounts payable",
        "schema_definition": {
            "sections": ["Header", "Line Items", "Totals"],
            "fields": [
                {"key": "vendor_name", "label": "Vendor Name", "data_type": "string", "section": "Header", "canonical_key": "entity.vendor_name"},
                {"key": "invoice_number", "label": "Invoice No.", "data_type": "id", "section": "Header", "canonical_key": "document.reference_number"},
                {"key": "invoice_date", "label": "Invoice Date", "data_type": "date", "section": "Header", "canonical_key": "document.date"},
                {"key": "subtotal_amount", "label": "Subtotal", "data_type": "money", "section": "Totals", "canonical_key": "financial.subtotal_amount"},
                {"key": "tax_amount", "label": "Tax Amount", "data_type": "money", "section": "Totals", "canonical_key": "financial.tax_amount"},
                {"key": "total_amount", "label": "Total Amount", "data_type": "money", "section": "Totals", "canonical_key": "financial.total_amount"},
            ],
            "tables": [
                {
                    "key": "items",
                    "title": "Line Items",
                    "columns": ["description", "quantity", "unit_price", "amount"],
                }
            ],
            "validation_rules": [
                {
                    "rule": "sum_equals",
                    "target": "total_amount",
                    "terms": ["items.amount", "tax_amount"],
                    "tolerance": 0.05,
                }
            ],
            "insight_definitions": [
                {"id": "ins_total_spend", "title": "Total Spend", "kind": "metric", "agg": "sum", "table": "items", "column": "amount"},
                {"id": "ins_item_count", "title": "Total Item Count", "kind": "metric", "agg": "count", "table": "items"},
            ],
        },
    },
    {
        "id": "sch_purchase_order_v1",
        "name": "Purchase Order",
        "family": "financial",
        "version": 1,
        "origin": "template",
        "description": "Procurement orders, PO confirmations, corporate buyer purchase orders",
        "schema_definition": {
            "sections": ["Order Header", "Parties", "Line Items", "Order Total"],
            "fields": [
                {"key": "po_number", "label": "PO Number", "data_type": "id", "section": "Order Header", "canonical_key": "document.reference_number"},
                {"key": "order_date", "label": "Order Date", "data_type": "date", "section": "Order Header", "canonical_key": "document.date"},
                {"key": "buyer_name", "label": "Buyer Name", "data_type": "string", "section": "Parties"},
                {"key": "supplier_name", "label": "Supplier Name", "data_type": "string", "section": "Parties", "canonical_key": "entity.vendor_name"},
                {"key": "total_amount", "label": "Total Amount", "data_type": "money", "section": "Order Total", "canonical_key": "financial.total_amount"},
            ],
            "tables": [
                {"key": "items", "title": "Ordered Items", "columns": ["item_name", "quantity", "unit_price", "total"]}
            ],
            "validation_rules": [
                {"rule": "sum_equals", "target": "total_amount", "terms": ["items.total"]}
            ],
            "insight_definitions": [],
        },
    },
    {
        "id": "sch_retail_receipt_v1",
        "name": "Store / Retail Receipt",
        "family": "financial",
        "version": 1,
        "origin": "template",
        "description": "Retail store, supermarket, restaurant, cafe, fuel receipts",
        "schema_definition": {
            "sections": ["Merchant Details", "Transaction Details", "Receipt Totals"],
            "fields": [
                {"key": "store_name", "label": "Store Name", "data_type": "string", "section": "Merchant Details", "canonical_key": "entity.vendor_name"},
                {"key": "receipt_number", "label": "Receipt No.", "data_type": "id", "section": "Transaction Details", "canonical_key": "document.reference_number"},
                {"key": "receipt_date", "label": "Date", "data_type": "date", "section": "Transaction Details", "canonical_key": "document.date"},
                {"key": "payment_method", "label": "Payment Method", "data_type": "string", "section": "Transaction Details"},
                {"key": "subtotal_amount", "label": "Subtotal", "data_type": "money", "section": "Receipt Totals", "canonical_key": "financial.subtotal_amount"},
                {"key": "tax_amount", "label": "Tax", "data_type": "money", "section": "Receipt Totals", "canonical_key": "financial.tax_amount"},
                {"key": "total_amount", "label": "Total Amount", "data_type": "money", "section": "Receipt Totals", "canonical_key": "financial.total_amount"},
            ],
            "tables": [
                {"key": "items", "title": "Purchased Items", "columns": ["item_name", "qty", "price"]}
            ],
            "validation_rules": [],
            "insight_definitions": [],
        },
    },
    {
        "id": "sch_bank_statement_v1",
        "name": "Bank Statement",
        "family": "financial",
        "version": 1,
        "origin": "template",
        "description": "Monthly bank account statements, ledger sheets, debit/credit records",
        "schema_definition": {
            "sections": ["Account Information", "Statement Period", "Balances"],
            "fields": [
                {"key": "account_holder", "label": "Account Holder", "data_type": "string", "section": "Account Information", "canonical_key": "person.account_holder"},
                {"key": "account_number", "label": "Account Number", "data_type": "id", "section": "Account Information", "canonical_key": "financial.account_number"},
                {"key": "statement_period", "label": "Statement Period", "data_type": "string", "section": "Statement Period"},
                {"key": "opening_balance", "label": "Opening Balance", "data_type": "money", "section": "Balances"},
                {"key": "closing_balance", "label": "Closing Balance", "data_type": "money", "section": "Balances"},
            ],
            "tables": [
                {
                    "key": "transactions",
                    "title": "Transactions",
                    "columns": ["date", "description", "debit", "credit", "balance"],
                }
            ],
            "validation_rules": [
                {
                    "rule": "running_balance",
                    "table": "transactions",
                    "opening": "opening_balance",
                    "debit": "debit",
                    "credit": "credit",
                    "balance": "balance",
                }
            ],
            "insight_definitions": [
                {"id": "ins_total_debit", "title": "Total Debits", "kind": "metric", "agg": "sum", "table": "transactions", "column": "debit"},
                {"id": "ins_total_credit", "title": "Total Credits", "kind": "metric", "agg": "sum", "table": "transactions", "column": "credit"},
            ],
        },
    },
    {
        "id": "sch_resume_v1",
        "name": "Resume / CV",
        "family": "employment",
        "version": 1,
        "origin": "template",
        "description": "Curriculum vitae, job applicant profiles, professional work experience",
        "schema_definition": {
            "sections": ["Personal Details", "Professional Summary", "Experience", "Education", "Skills & Projects"],
            "fields": [
                {"key": "candidate_name", "label": "Candidate Name", "data_type": "string", "section": "Personal Details", "canonical_key": "person.full_name"},
                {"key": "email", "label": "Email Address", "data_type": "email", "section": "Personal Details", "canonical_key": "person.email"},
                {"key": "phone", "label": "Phone Number", "data_type": "phone", "section": "Personal Details", "canonical_key": "person.phone"},
                {"key": "summary", "label": "Professional Summary", "data_type": "text", "section": "Professional Summary"},
                {"key": "skills", "label": "Technical Skills", "data_type": "text", "section": "Skills & Projects"},
                {"key": "education", "label": "Education History", "data_type": "text", "section": "Education"},
                {"key": "experience", "label": "Work Experience", "data_type": "text", "section": "Experience"},
                {"key": "projects", "label": "Featured Projects", "data_type": "text", "section": "Skills & Projects"},
            ],
            "tables": [],
            "validation_rules": [],
            "insight_definitions": [],
        },
    },
    {
        "id": "sch_certificate_v1",
        "name": "Certificate",
        "family": "academic",
        "version": 1,
        "origin": "template",
        "description": "Academic degrees, course completions, professional accreditations",
        "schema_definition": {
            "sections": ["Certificate Overview", "Recipient Details", "Issuing Authority"],
            "fields": [
                {"key": "recipient_name", "label": "Recipient Name", "data_type": "string", "section": "Recipient Details", "canonical_key": "person.full_name"},
                {"key": "credential_title", "label": "Degree / Credential Title", "data_type": "string", "section": "Certificate Overview"},
                {"key": "issuing_organization", "label": "Issuing Authority", "data_type": "string", "section": "Issuing Authority"},
                {"key": "issue_date", "label": "Issue Date", "data_type": "date", "section": "Certificate Overview", "canonical_key": "document.date"},
                {"key": "certificate_id", "label": "Certificate / Reg ID", "data_type": "id", "section": "Certificate Overview"},
            ],
            "tables": [],
            "validation_rules": [],
            "insight_definitions": [],
        },
    },
    {
        "id": "sch_contract_v1",
        "name": "Contract / Agreement",
        "family": "legal",
        "version": 1,
        "origin": "template",
        "description": "Legal agreements, service agreements, NDAs, leases",
        "schema_definition": {
            "sections": ["Parties", "Term & Duration", "Terms & Scope"],
            "fields": [
                {"key": "primary_parties", "label": "Contracting Parties", "data_type": "text", "section": "Parties"},
                {"key": "effective_date", "label": "Effective Date", "data_type": "date", "section": "Term & Duration", "canonical_key": "document.date"},
                {"key": "expiration_date", "label": "Expiration Date", "data_type": "date", "section": "Term & Duration"},
                {"key": "governing_law", "label": "Governing Law / Jurisdiction", "data_type": "string", "section": "Terms & Scope"},
                {"key": "terms_summary", "label": "Key Terms Summary", "data_type": "text", "section": "Terms & Scope"},
            ],
            "tables": [],
            "validation_rules": [
                {"rule": "date_order", "earlier": "effective_date", "later": "expiration_date"}
            ],
            "insight_definitions": [],
        },
    },
    {
        "id": "sch_delivery_challan_v1",
        "name": "Delivery Challan",
        "family": "logistics",
        "version": 1,
        "origin": "template",
        "description": "Goods delivery notes, dispatch receipts, shipment dispatches",
        "schema_definition": {
            "sections": ["Dispatch Details", "Consignor & Consignee", "Items Dispatched"],
            "fields": [
                {"key": "challan_number", "label": "Challan Number", "data_type": "id", "section": "Dispatch Details", "canonical_key": "document.reference_number"},
                {"key": "challan_date", "label": "Date", "data_type": "date", "section": "Dispatch Details", "canonical_key": "document.date"},
                {"key": "sender_name", "label": "Consignor / Sender", "data_type": "string", "section": "Consignor & Consignee"},
                {"key": "receiver_name", "label": "Consignee / Receiver", "data_type": "string", "section": "Consignor & Consignee"},
                {"key": "vehicle_number", "label": "Vehicle / Transport No.", "data_type": "string", "section": "Dispatch Details"},
            ],
            "tables": [
                {"key": "items", "title": "Dispatched Goods", "columns": ["description", "quantity", "unit"]}
            ],
            "validation_rules": [],
            "insight_definitions": [],
        },
    },
    {
        "id": "sch_medical_report_v1",
        "name": "Medical Report",
        "family": "medical",
        "version": 1,
        "origin": "template",
        "description": "Clinical lab reports, diagnostic test sheets, hospital discharge summaries",
        "schema_definition": {
            "sections": ["Patient Information", "Clinical Details", "Lab Test Results"],
            "fields": [
                {"key": "patient_name", "label": "Patient Name", "data_type": "string", "section": "Patient Information", "canonical_key": "person.full_name"},
                {"key": "patient_age_gender", "label": "Age / Gender", "data_type": "string", "section": "Patient Information"},
                {"key": "referring_doctor", "label": "Referring Doctor", "data_type": "string", "section": "Clinical Details"},
                {"key": "report_date", "label": "Report Date", "data_type": "date", "section": "Clinical Details", "canonical_key": "document.date"},
                {"key": "diagnosis", "label": "Impression / Diagnosis", "data_type": "text", "section": "Clinical Details"},
            ],
            "tables": [
                {
                    "key": "test_results",
                    "title": "Investigation Results",
                    "columns": ["test_name", "result_value", "unit", "reference_interval"],
                }
            ],
            "validation_rules": [],
            "insight_definitions": [],
        },
    },
    {
        "id": "sch_insurance_v1",
        "name": "Insurance Document",
        "family": "financial",
        "version": 1,
        "origin": "template",
        "description": "Insurance policy schedules, premium receipts, claim forms",
        "schema_definition": {
            "sections": ["Policy Details", "Policyholder", "Coverage & Premiums"],
            "fields": [
                {"key": "policy_number", "label": "Policy Number", "data_type": "id", "section": "Policy Details", "canonical_key": "document.reference_number"},
                {"key": "policy_holder", "label": "Policyholder Name", "data_type": "string", "section": "Policyholder", "canonical_key": "person.full_name"},
                {"key": "start_date", "label": "Coverage Start Date", "data_type": "date", "section": "Policy Details"},
                {"key": "end_date", "label": "Coverage End Date", "data_type": "date", "section": "Policy Details"},
                {"key": "sum_insured", "label": "Sum Insured", "data_type": "money", "section": "Coverage & Premiums"},
                {"key": "premium_amount", "label": "Premium Amount", "data_type": "money", "section": "Coverage & Premiums"},
            ],
            "tables": [],
            "validation_rules": [
                {"rule": "date_order", "earlier": "start_date", "later": "end_date"}
            ],
            "insight_definitions": [],
        },
    },
    {
        "id": "sch_id_document_v1",
        "name": "ID Document",
        "family": "identity",
        "version": 1,
        "origin": "template",
        "description": "Passports, national ID cards, driver licenses, PAN, Aadhaar",
        "schema_definition": {
            "sections": ["Identity Details", "Holder Information"],
            "fields": [
                {"key": "document_id_number", "label": "ID Number", "data_type": "id", "section": "Identity Details", "canonical_key": "document.reference_number"},
                {"key": "full_name", "label": "Full Name", "data_type": "string", "section": "Holder Information", "canonical_key": "person.full_name"},
                {"key": "date_of_birth", "label": "Date of Birth", "data_type": "date", "section": "Holder Information"},
                {"key": "address", "label": "Address", "data_type": "text", "section": "Holder Information"},
                {"key": "expiry_date", "label": "Expiry Date", "data_type": "date", "section": "Identity Details"},
            ],
            "tables": [],
            "validation_rules": [],
            "insight_definitions": [],
        },
    },
    {
        "id": "sch_expense_report_v1",
        "name": "Expense Report",
        "family": "financial",
        "version": 1,
        "origin": "template",
        "description": "Employee business travel expenses, reimbursement claims",
        "schema_definition": {
            "sections": ["Employee Information", "Expense Period", "Summary Totals"],
            "fields": [
                {"key": "employee_name", "label": "Employee Name", "data_type": "string", "section": "Employee Information", "canonical_key": "person.full_name"},
                {"key": "employee_id", "label": "Employee ID", "data_type": "id", "section": "Employee Information"},
                {"key": "report_date", "label": "Report Date", "data_type": "date", "section": "Expense Period", "canonical_key": "document.date"},
                {"key": "total_amount", "label": "Total Reimbursement Claimed", "data_type": "money", "section": "Summary Totals", "canonical_key": "financial.total_amount"},
            ],
            "tables": [
                {"key": "expenses", "title": "Itemized Expenses", "columns": ["date", "category", "description", "amount"]}
            ],
            "validation_rules": [
                {"rule": "sum_equals", "target": "total_amount", "terms": ["expenses.amount"]}
            ],
            "insight_definitions": [],
        },
    },
    {
        "id": "sch_application_form_v1",
        "name": "Application / Form",
        "family": "general",
        "version": 1,
        "origin": "template",
        "description": "Enrollment applications, registration forms, survey questionnaires",
        "schema_definition": {
            "sections": ["Applicant Details", "Application Meta", "Form Fields"],
            "fields": [
                {"key": "applicant_name", "label": "Applicant Name", "data_type": "string", "section": "Applicant Details", "canonical_key": "person.full_name"},
                {"key": "application_id", "label": "Application ID", "data_type": "id", "section": "Application Meta", "canonical_key": "document.reference_number"},
                {"key": "submission_date", "label": "Submission Date", "data_type": "date", "section": "Application Meta", "canonical_key": "document.date"},
                {"key": "form_summary", "label": "Summary / Status", "data_type": "text", "section": "Form Fields"},
            ],
            "tables": [],
            "validation_rules": [],
            "insight_definitions": [],
        },
    },
]
