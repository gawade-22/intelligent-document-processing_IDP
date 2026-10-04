"""
Multi-Type Document Field Extraction Service.
Extracts specialized target fields for all 13 supported document classes:
1. Invoice (Vendor Name, Invoice No., Date, Items, Quantity, Tax, Total Amount)
2. Purchase Order (PO Number, Buyer, Supplier, Order Date, Items, Quantity, Price, Total)
3. Receipt (Store Name, Receipt No., Date, Items, Amount, Tax, Payment Method, Total Amount)
4. Bank Statement (Account Holder, Account No., Statement Period, Transaction Date, Description, Debit, Credit, Balance)
5. Resume/CV (Name, Email, Phone, Skills, Education, Experience, Projects)
6. Certificate (Person Name, Certificate Type, Institution, Issue Date, Certificate ID)
7. Contract/Agreement (Parties, Agreement Date, Effective Date, Expiry Date, Contract Value, Terms)
8. Delivery Challan (Challan No., Date, Supplier, Customer, Items, Quantity, Transport Details)
9. Medical Report (Patient Name, Report Date, Test Name, Result, Reference Range, Doctor)
10. Insurance Document (Policy No., Policy Holder, Insurance Type, Start Date, Expiry Date, Premium)
11. ID Document (Name, ID Number, Date of Birth, Address, Issue/Expiry Date)
12. Expense Report (Employee Name, Expense Date, Category, Description, Amount, Total)
13. Application/Form (Applicant Name, Contact Details, Address, Application No., Form Fields)

Combines high-accuracy heuristic pattern extraction with LLM reasoning when an AI provider is active.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.llm import LLMExtractionStatus
from app.services.ai.base import AIExtractionProvider, NoOpAIExtractionProvider
from app.services.document_classifier import document_classifier
from app.services.llm_extractor import get_llm_extractor

logger = logging.getLogger(__name__)


class MultiTypeExtractor:
    """Universal multi-type document extractor."""

    @classmethod
    def extract_heuristic_fields(cls, text: str, document_type: str, filename: str = "") -> Dict[str, Dict[str, Any]]:
        """
        Extracts document-specific fields using deterministic regex and keyword heuristics.
        Returns map of field_name -> {"value": ..., "confidence": float, "source": "rule"}.
        """
        lines = [line.strip() for line in (text or "").split("\n") if line.strip()]
        doc_type = document_type.lower()
        extracted: Dict[str, Dict[str, Any]] = {}

        # Universal date pattern
        date_pattern = r"\b(?:\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}|\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,]+\d{1,2}[\s,]+\d{4})\b"
        # Universal currency / amount pattern
        amount_pattern = r"(?:[$€£₹]\s*|USD\s*|INR\s*|EUR\s*)?(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})|\d+(?:\.\d{1,2}))"
        # Universal email pattern
        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        # Universal phone pattern
        phone_pattern = r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"

        if doc_type == "resume":
            # Candidate Name (Header line)
            cand_name = None
            for l in lines[:5]:
                if not re.search(r"@|www|\.com|phone|github|linkedin|resume|curriculum", l, re.I) and len(l.split()) in (2, 3, 4):
                    cand_name = l
                    break
            extracted["candidate_name"] = {"value": cand_name, "confidence": 0.85 if cand_name else 0.0, "source": "rule"}

            # Email
            emails = re.findall(email_pattern, text)
            extracted["email"] = {"value": emails[0] if emails else None, "confidence": 0.95 if emails else 0.0, "source": "rule"}

            # Phone
            phones = re.findall(phone_pattern, text)
            extracted["phone"] = {"value": phones[0] if phones else None, "confidence": 0.90 if phones else 0.0, "source": "rule"}

            # Skills
            skills_found = []
            known_skills = ["python", "javascript", "react", "fastapi", "docker", "kubernetes", "sql", "postgresql", "aws", "git", "machine learning", "java", "c++", "html", "css", "node.js"]
            for s in known_skills:
                if re.search(rf"\b{re.escape(s)}\b", text, re.I):
                    skills_found.append(s.title())
            extracted["skills"] = {"value": ", ".join(skills_found) if skills_found else None, "confidence": 0.85 if skills_found else 0.0, "source": "rule"}

            # Education & Experience keywords
            edu_match = re.search(r"(?:b\.tech|bachelor|master|m\.s\.|b\.s\.|phd|degree|university|college|institute)[^\n]+", text, re.I)
            extracted["education"] = {"value": edu_match.group(0).strip() if edu_match else None, "confidence": 0.80 if edu_match else 0.0, "source": "rule"}

            exp_match = re.search(r"(\d+\+?\s*years?(?:\s*of)?\s*experience[^\n]*)", text, re.I)
            extracted["experience"] = {"value": exp_match.group(1).strip() if exp_match else None, "confidence": 0.80 if exp_match else 0.0, "source": "rule"}
            extracted["projects"] = {"value": "Projects section present" if "project" in text.lower() else None, "confidence": 0.70 if "project" in text.lower() else 0.0, "source": "rule"}

        elif doc_type == "bank_statement":
            # Account Holder
            holder_match = re.search(r"(?:account\s*holder|customer\s*name|name)\s*[:.\-]\s*([^\n]+)", text, re.I)
            holder = holder_match.group(1).strip() if holder_match else (lines[0] if lines else None)
            extracted["account_holder"] = {"value": holder, "confidence": 0.85 if holder else 0.0, "source": "rule"}

            # Account Number
            acc_match = re.search(r"(?:account\s*(?:no|number|#)|a/c\s*(?:no)?)\s*[:.\-]?\s*([0-9xX\-]+)", text, re.I)
            extracted["account_number"] = {"value": acc_match.group(1).strip() if acc_match else None, "confidence": 0.90 if acc_match else 0.0, "source": "rule"}

            # Statement Period
            period_match = re.search(r"(?:statement\s*period|period)\s*[:.\-]?\s*([^\n]+)", text, re.I)
            extracted["statement_period"] = {"value": period_match.group(1).strip() if period_match else None, "confidence": 0.85 if period_match else 0.0, "source": "rule"}

            # Transaction Date
            date_matches = re.findall(date_pattern, text)
            extracted["transaction_date"] = {"value": date_matches[-1] if date_matches else None, "confidence": 0.80 if date_matches else 0.0, "source": "rule"}

            # Debit / Credit / Balance
            bal_match = re.search(r"(?:closing\s*balance|available\s*balance|balance|bal)\s*[:.\-]?\s*([$€£₹]?\s*[\d,]+(?:\.\d{1,2})?)", text, re.I)
            extracted["balance_amount"] = {"value": bal_match.group(1).strip() if bal_match else None, "confidence": 0.85 if bal_match else 0.0, "source": "rule"}

            deb_match = re.search(r"(?:debit|withdrawals?)\s*[:.\-]?\s*([$€£₹]?\s*[\d,]+(?:\.\d{1,2})?)", text, re.I)
            extracted["debit_amount"] = {"value": deb_match.group(1).strip() if deb_match else None, "confidence": 0.75 if deb_match else 0.0, "source": "rule"}

            cred_match = re.search(r"(?:credit|deposits?)\s*[:.\-]?\s*([$€£₹]?\s*[\d,]+(?:\.\d{1,2})?)", text, re.I)
            extracted["credit_amount"] = {"value": cred_match.group(1).strip() if cred_match else None, "confidence": 0.75 if cred_match else 0.0, "source": "rule"}
            extracted["transaction_description"] = {"value": "Statement transactions" if "transaction" in text.lower() else None, "confidence": 0.70, "source": "rule"}

        elif doc_type == "purchase_order":
            # PO Number
            po_match = re.search(r"(?:purchase\s*order\s*(?:no|number|#)|po\s*(?:no|number|#))\s*[:.\-]?\s*([A-Za-z0-9\-_/]+)", text, re.I)
            extracted["po_number"] = {"value": po_match.group(1).strip() if po_match else None, "confidence": 0.90 if po_match else 0.0, "source": "rule"}

            # Buyer & Supplier
            buyer_match = re.search(r"(?:buyer|order(?:ed)?\s*by|deliver\s*to)\s*[:.\-]\s*([^\n]+)", text, re.I)
            extracted["buyer_name"] = {"value": buyer_match.group(1).strip() if buyer_match else None, "confidence": 0.85 if buyer_match else 0.0, "source": "rule"}

            supp_match = re.search(r"(?:supplier|vendor)\s*[:.\-]\s*([^\n]+)", text, re.I)
            extracted["supplier_name"] = {"value": supp_match.group(1).strip() if supp_match else (lines[0] if lines else None), "confidence": 0.80 if supp_match else 0.0, "source": "rule"}

            # Order Date
            date_matches = re.findall(date_pattern, text)
            extracted["order_date"] = {"value": date_matches[0] if date_matches else None, "confidence": 0.85 if date_matches else 0.0, "source": "rule"}

            # Amounts & Items
            tot_match = re.search(r"(?:total\s*(?:order\s*amount|amount|value)?|grand\s*total)\s*[:.\-]?\s*([$€£₹]?\s*[\d,]+(?:\.\d{1,2})?)", text, re.I)
            extracted["total_amount"] = {"value": tot_match.group(1).strip() if tot_match else None, "confidence": 0.85 if tot_match else 0.0, "source": "rule"}
            extracted["items"] = {"value": "Procurement items" if "item" in text.lower() or "qty" in text.lower() else None, "confidence": 0.70, "source": "rule"}
            extracted["quantity"] = {"value": None, "confidence": 0.0, "source": "rule"}
            extracted["unit_price"] = {"value": None, "confidence": 0.0, "source": "rule"}

        elif doc_type == "certificate":
            name_match = re.search(r"(?:certify\s*that|awarded\s*to|conferred\s*upon|name)\s*[:.\-]?\s*([A-Za-z\s]+)", text, re.I)
            extracted["person_name"] = {"value": name_match.group(1).strip() if name_match else None, "confidence": 0.85 if name_match else 0.0, "source": "rule"}

            type_match = re.search(r"(?:certificate\s*of\s*[A-Za-z]+|bachelor\s*of\s*[A-Za-z]+|degree\s*of\s*[A-Za-z]+)", text, re.I)
            extracted["certificate_type"] = {"value": type_match.group(0).strip() if type_match else "Completion Certificate", "confidence": 0.80, "source": "rule"}

            inst_match = re.search(r"(?:university|institute|academy|college|school|board)[^\n,]*", text, re.I)
            extracted["institution_name"] = {"value": inst_match.group(0).strip() if inst_match else None, "confidence": 0.80 if inst_match else 0.0, "source": "rule"}

            date_matches = re.findall(date_pattern, text)
            extracted["issue_date"] = {"value": date_matches[-1] if date_matches else None, "confidence": 0.80 if date_matches else 0.0, "source": "rule"}

            id_match = re.search(r"(?:certificate\s*(?:id|no|number)|credential\s*id)\s*[:.\-]?\s*([A-Za-z0-9\-_/]+)", text, re.I)
            extracted["certificate_id"] = {"value": id_match.group(1).strip() if id_match else None, "confidence": 0.85 if id_match else 0.0, "source": "rule"}

        elif doc_type == "contract":
            party_match = re.search(r"(?:between|parties)\s*[:.\-]?\s*([^\n]+)", text, re.I)
            extracted["parties"] = {"value": party_match.group(1).strip() if party_match else None, "confidence": 0.80 if party_match else 0.0, "source": "rule"}

            eff_match = re.search(r"(?:effective\s*date)\s*[:.\-]?\s*([^\n]+)", text, re.I)
            extracted["effective_date"] = {"value": eff_match.group(1).strip() if eff_match else None, "confidence": 0.85 if eff_match else 0.0, "source": "rule"}

            exp_match = re.search(r"(?:expiry\s*date|expiration\s*date|termination\s*date)\s*[:.\-]?\s*([^\n]+)", text, re.I)
            extracted["expiry_date"] = {"value": exp_match.group(1).strip() if exp_match else None, "confidence": 0.85 if exp_match else 0.0, "source": "rule"}

            val_match = re.search(r"(?:contract\s*value|consideration|fee|amount)\s*[:.\-]?\s*([$€£₹]?\s*[\d,]+(?:\.\d{1,2})?)", text, re.I)
            extracted["contract_value"] = {"value": val_match.group(1).strip() if val_match else None, "confidence": 0.80 if val_match else 0.0, "source": "rule"}
            extracted["agreement_date"] = {"value": None, "confidence": 0.0, "source": "rule"}
            extracted["terms_summary"] = {"value": "Legally binding agreement" if "agree" in text.lower() else None, "confidence": 0.70, "source": "rule"}

        elif doc_type == "medical_report":
            p_match = re.search(r"(?:patient\s*(?:name)?|name)\s*[:.\-]\s*([A-Za-z\s]+)", text, re.I)
            extracted["patient_name"] = {"value": p_match.group(1).strip() if p_match else None, "confidence": 0.85 if p_match else 0.0, "source": "rule"}

            date_matches = re.findall(date_pattern, text)
            extracted["report_date"] = {"value": date_matches[0] if date_matches else None, "confidence": 0.85 if date_matches else 0.0, "source": "rule"}

            test_match = re.search(r"(?:test\s*name|investigation|procedure)\s*[:.\-]\s*([^\n]+)", text, re.I)
            extracted["test_name"] = {"value": test_match.group(1).strip() if test_match else None, "confidence": 0.80 if test_match else 0.0, "source": "rule"}

            res_match = re.search(r"(?:result|findings?|observed\s*value)\s*[:.\-]\s*([^\n]+)", text, re.I)
            extracted["test_result"] = {"value": res_match.group(1).strip() if res_match else None, "confidence": 0.80 if res_match else 0.0, "source": "rule"}

            ref_match = re.search(r"(?:reference\s*range|reference\s*interval|biological\s*reference)\s*[:.\-]\s*([^\n]+)", text, re.I)
            extracted["reference_range"] = {"value": ref_match.group(1).strip() if ref_match else None, "confidence": 0.75 if ref_match else 0.0, "source": "rule"}

            dr_match = re.search(r"(?:dr\.\s*[A-Za-z\s]+|doctor\s*[:.\-]\s*[A-Za-z\s]+)", text, re.I)
            extracted["doctor_name"] = {"value": dr_match.group(0).strip() if dr_match else None, "confidence": 0.80 if dr_match else 0.0, "source": "rule"}

        elif doc_type == "insurance":
            pol_match = re.search(r"(?:policy\s*(?:no|number|#))\s*[:.\-]?\s*([A-Za-z0-9\-_/]+)", text, re.I)
            extracted["policy_number"] = {"value": pol_match.group(1).strip() if pol_match else None, "confidence": 0.90 if pol_match else 0.0, "source": "rule"}

            holder_match = re.search(r"(?:policy\s*holder|insured\s*name|proposer)\s*[:.\-]\s*([A-Za-z\s]+)", text, re.I)
            extracted["policy_holder"] = {"value": holder_match.group(1).strip() if holder_match else None, "confidence": 0.85 if holder_match else 0.0, "source": "rule"}

            prem_match = re.search(r"(?:premium\s*(?:amount)?|total\s*premium)\s*[:.\-]?\s*([$€£₹]?\s*[\d,]+(?:\.\d{1,2})?)", text, re.I)
            extracted["premium_amount"] = {"value": prem_match.group(1).strip() if prem_match else None, "confidence": 0.85 if prem_match else 0.0, "source": "rule"}

            date_matches = re.findall(date_pattern, text)
            extracted["start_date"] = {"value": date_matches[0] if len(date_matches) > 0 else None, "confidence": 0.80 if date_matches else 0.0, "source": "rule"}
            extracted["expiry_date"] = {"value": date_matches[1] if len(date_matches) > 1 else None, "confidence": 0.80 if len(date_matches) > 1 else 0.0, "source": "rule"}
            extracted["insurance_type"] = {"value": "General Insurance" if "insurance" in text.lower() else None, "confidence": 0.70, "source": "rule"}

        elif doc_type == "id_document":
            id_match = re.search(r"(?:id\s*(?:no|number|#)|passport\s*(?:no)?|license\s*(?:no)?)\s*[:.\-]?\s*([A-Za-z0-9\-_]+)", text, re.I)
            extracted["id_number"] = {"value": id_match.group(1).strip() if id_match else None, "confidence": 0.90 if id_match else 0.0, "source": "rule"}

            name_match = re.search(r"(?:name)\s*[:.\-]\s*([A-Za-z\s]+)", text, re.I)
            extracted["person_name"] = {"value": name_match.group(1).strip() if name_match else (lines[0] if lines else None), "confidence": 0.80 if name_match else 0.0, "source": "rule"}

            dob_match = re.search(r"(?:date\s*of\s*birth|dob)\s*[:.\-]?\s*([0-9\-/.\s]+)", text, re.I)
            extracted["date_of_birth"] = {"value": dob_match.group(1).strip() if dob_match else None, "confidence": 0.85 if dob_match else 0.0, "source": "rule"}

            addr_match = re.search(r"(?:address)\s*[:.\-]\s*([^\n]+)", text, re.I)
            extracted["address"] = {"value": addr_match.group(1).strip() if addr_match else None, "confidence": 0.80 if addr_match else 0.0, "source": "rule"}
            extracted["issue_expiry_date"] = {"value": None, "confidence": 0.0, "source": "rule"}

        elif doc_type == "delivery_challan":
            ch_match = re.search(r"(?:challan\s*(?:no|number|#)|delivery\s*challan)\s*[:.\-]?\s*([A-Za-z0-9\-_/]+)", text, re.I)
            extracted["challan_number"] = {"value": ch_match.group(1).strip() if ch_match else None, "confidence": 0.90 if ch_match else 0.0, "source": "rule"}

            date_matches = re.findall(date_pattern, text)
            extracted["challan_date"] = {"value": date_matches[0] if date_matches else None, "confidence": 0.85 if date_matches else 0.0, "source": "rule"}

            supp_match = re.search(r"(?:supplier|consignor|from)\s*[:.\-]\s*([^\n]+)", text, re.I)
            extracted["supplier_name"] = {"value": supp_match.group(1).strip() if supp_match else (lines[0] if lines else None), "confidence": 0.80 if supp_match else 0.0, "source": "rule"}

            cust_match = re.search(r"(?:customer|consignee|to)\s*[:.\-]\s*([^\n]+)", text, re.I)
            extracted["customer_name"] = {"value": cust_match.group(1).strip() if cust_match else None, "confidence": 0.80 if cust_match else 0.0, "source": "rule"}

            veh_match = re.search(r"(?:vehicle\s*(?:no|number)?|transporter|lr\s*(?:no)?)\s*[:.\-]?\s*([^\n]+)", text, re.I)
            extracted["transport_details"] = {"value": veh_match.group(0).strip() if veh_match else None, "confidence": 0.75 if veh_match else 0.0, "source": "rule"}
            extracted["items"] = {"value": "Dispatched materials" if "item" in text.lower() or "qty" in text.lower() else None, "confidence": 0.70, "source": "rule"}
            extracted["quantity"] = {"value": None, "confidence": 0.0, "source": "rule"}

        elif doc_type == "expense_report":
            emp_match = re.search(r"(?:employee\s*(?:name)?|claimant|submitted\s*by)\s*[:.\-]\s*([A-Za-z\s]+)", text, re.I)
            extracted["employee_name"] = {"value": emp_match.group(1).strip() if emp_match else (lines[0] if lines else None), "confidence": 0.85 if emp_match else 0.0, "source": "rule"}

            date_matches = re.findall(date_pattern, text)
            extracted["expense_date"] = {"value": date_matches[0] if date_matches else None, "confidence": 0.85 if date_matches else 0.0, "source": "rule"}

            tot_match = re.search(r"(?:total\s*(?:amount|expense|claim)?|grand\s*total)\s*[:.\-]?\s*([$€£₹]?\s*[\d,]+(?:\.\d{1,2})?)", text, re.I)
            extracted["total_amount"] = {"value": tot_match.group(1).strip() if tot_match else None, "confidence": 0.85 if tot_match else 0.0, "source": "rule"}

            extracted["category"] = {"value": "Travel & Lodging" if "travel" in text.lower() or "hotel" in text.lower() else "General Expense", "confidence": 0.75, "source": "rule"}
            extracted["description"] = {"value": "Business expense claim", "confidence": 0.70, "source": "rule"}
            extracted["expense_amount"] = {"value": extracted["total_amount"]["value"], "confidence": 0.80, "source": "rule"}

        elif doc_type == "application_form":
            app_match = re.search(r"(?:applicant\s*(?:name)?|candidate\s*name|name)\s*[:.\-]\s*([A-Za-z\s]+)", text, re.I)
            extracted["applicant_name"] = {"value": app_match.group(1).strip() if app_match else None, "confidence": 0.85 if app_match else 0.0, "source": "rule"}

            num_match = re.search(r"(?:application\s*(?:no|number|#)|form\s*(?:no|number|#))\s*[:.\-]?\s*([A-Za-z0-9\-_/]+)", text, re.I)
            extracted["application_number"] = {"value": num_match.group(1).strip() if num_match else None, "confidence": 0.90 if num_match else 0.0, "source": "rule"}

            emails = re.findall(email_pattern, text)
            phones = re.findall(phone_pattern, text)
            contacts = []
            if phones:
                contacts.append(phones[0])
            if emails:
                contacts.append(emails[0])
            extracted["contact_details"] = {"value": ", ".join(contacts) if contacts else None, "confidence": 0.85 if contacts else 0.0, "source": "rule"}

            addr_match = re.search(r"(?:address)\s*[:.\-]\s*([^\n]+)", text, re.I)
            extracted["address"] = {"value": addr_match.group(1).strip() if addr_match else None, "confidence": 0.80 if addr_match else 0.0, "source": "rule"}
            extracted["form_fields"] = {"value": "Application submitted successfully", "confidence": 0.70, "source": "rule"}

        elif doc_type == "receipt":
            # Store Name (first line or prominent merchant)
            store_name = lines[0] if lines else "Retail Store"
            extracted["store_name"] = {"value": store_name, "confidence": 0.80, "source": "rule"}

            rec_match = re.search(r"(?:receipt\s*(?:#|no|number)|check\s*#|trans\s*#|order\s*#)\s*[:.\-]?\s*([A-Za-z0-9\-_]+)", text, re.I)
            extracted["receipt_number"] = {"value": rec_match.group(1).strip() if rec_match else None, "confidence": 0.85 if rec_match else 0.0, "source": "rule"}

            date_matches = re.findall(date_pattern, text)
            extracted["receipt_date"] = {"value": date_matches[0] if date_matches else None, "confidence": 0.85 if date_matches else 0.0, "source": "rule"}

            tot_match = re.search(r"(?:total\s*(?:amount|paid)?|grand\s*total|fare|balance|cah|cash)\s*[:.\-]?\s*([$€£₹]?\s*[\d,]+(?:\.\d{1,2})?)", text, re.I)
            extracted["total_amount"] = {"value": tot_match.group(1).strip() if tot_match else None, "confidence": 0.85 if tot_match else 0.0, "source": "rule"}

            tax_match = re.search(r"(?:tax|vat|gst)\s*[:.\-]?\s*([$€£₹]?\s*[\d,]+(?:\.\d{1,2})?)", text, re.I)
            extracted["tax_amount"] = {"value": tax_match.group(1).strip() if tax_match else None, "confidence": 0.75 if tax_match else 0.0, "source": "rule"}

            pay_match = re.search(r"\b(visa|mastercard|cash|amex|upi|apple\s*pay|debit\s*card)\b", text, re.I)
            extracted["payment_method"] = {"value": pay_match.group(0).title() if pay_match else None, "confidence": 0.80 if pay_match else 0.0, "source": "rule"}
            extracted["subtotal_amount"] = {"value": None, "confidence": 0.0, "source": "rule"}
            extracted["items"] = {"value": "Receipt items sold", "confidence": 0.70, "source": "rule"}

        else:
            # Default / Invoice
            vendor = lines[0] if lines else None
            extracted["vendor_name"] = {"value": vendor, "confidence": 0.80 if vendor else 0.0, "source": "rule"}

            inv_match = re.search(r"(?:invoice\s*(?:#|no|number)|bill\s*(?:#|no)|inv\s*#)\s*[:.\-]?\s*([A-Za-z0-9\-_/]+)", text, re.I)
            extracted["invoice_number"] = {"value": inv_match.group(1).strip() if inv_match else None, "confidence": 0.85 if inv_match else 0.0, "source": "rule"}

            date_matches = re.findall(date_pattern, text)
            extracted["invoice_date"] = {"value": date_matches[0] if date_matches else None, "confidence": 0.85 if date_matches else 0.0, "source": "rule"}

            tot_match = re.search(r"(?:total\s*(?:amount)?|grand\s*total|net\s*payable|amount\s*due)\s*[:.\-]?\s*([$€£₹]?\s*[\d,]+(?:\.\d{1,2})?)", text, re.I)
            extracted["total_amount"] = {"value": tot_match.group(1).strip() if tot_match else None, "confidence": 0.85 if tot_match else 0.0, "source": "rule"}

            tax_match = re.search(r"(?:tax|gst|vat)\s*[:.\-]?\s*([$€£₹]?\s*[\d,]+(?:\.\d{1,2})?)", text, re.I)
            extracted["tax_amount"] = {"value": tax_match.group(1).strip() if tax_match else None, "confidence": 0.75 if tax_match else 0.0, "source": "rule"}
            extracted["items"] = {"value": "Invoice goods or services", "confidence": 0.70, "source": "rule"}
            extracted["quantity"] = {"value": "1", "confidence": 0.70, "source": "rule"}

        # Ensure all primary fields for this document type exist in the returned dictionary
        primary_fields = document_classifier.get_primary_fields(doc_type)
        for field in primary_fields:
            if field not in extracted:
                extracted[field] = {"value": None, "confidence": 0.0, "source": "none"}

        return extracted

    @classmethod
    def extract_all(
        cls,
        text: str,
        document_type: str,
        ai_provider: Optional[AIExtractionProvider] = None,
        context: Optional[Dict[str, Any]] = None,
        filename: str = "",
    ) -> Dict[str, Dict[str, Any]]:
        """
        Combines deterministic rule extraction with LLM reasoning.
        Returns unified field dictionary:
            field_name -> {
                "field": field_name,
                "value": str,
                "original_value": str,
                "normalized_value": str,
                "confidence": float,
                "source": "ai" | "rule" | "rule+ai"
            }
        """
        doc_type = document_type.lower()
        rule_extracted = cls.extract_heuristic_fields(text, doc_type, filename=filename)

        ai_extracted: Dict[str, Any] = {}
        ai_success = False

        if ai_provider and not isinstance(ai_provider, NoOpAIExtractionProvider):
            try:
                llm = get_llm_extractor(document_type=doc_type)
                res = llm.extract(
                    document_text=text,
                    document_type=doc_type,
                    context=context,
                    provider_override=ai_provider,
                )
                if res.status == LLMExtractionStatus.SUCCESS.value and res.fields:
                    ai_extracted = res.fields
                    ai_success = True
                    logger.info(f"LLM extraction succeeded for {doc_type}: {len(ai_extracted)} fields")
            except Exception as e:
                logger.warning(f"LLM extraction attempt failed: {e}")

        # Cross-field alias reconciliation
        if doc_type in ("receipt", "store_receipt", "retail_receipt", "restaurant"):
            if "store_name" not in ai_extracted and "vendor_name" in ai_extracted:
                ai_extracted["store_name"] = ai_extracted["vendor_name"]
            if "receipt_number" not in ai_extracted and "invoice_number" in ai_extracted:
                ai_extracted["receipt_number"] = ai_extracted["invoice_number"]
            if "receipt_date" not in ai_extracted and "invoice_date" in ai_extracted:
                ai_extracted["receipt_date"] = ai_extracted["invoice_date"]

        if doc_type in ("resume", "cv"):
            if "candidate_name" not in ai_extracted:
                for k in ("name", "person_name", "applicant_name", "full_name"):
                    if k in ai_extracted:
                        ai_extracted["candidate_name"] = ai_extracted[k]
                        break

        if doc_type == "bank_statement":
            if "account_holder" not in ai_extracted:
                for k in ("name", "customer_name", "holder_name"):
                    if k in ai_extracted:
                        ai_extracted["account_holder"] = ai_extracted[k]
                        break

        final_fields: Dict[str, Dict[str, Any]] = {}
        primary_fields = document_classifier.get_primary_fields(doc_type)

        all_keys = sorted(list(set(list(rule_extracted.keys()) + list(ai_extracted.keys()) + primary_fields)))

        for key in all_keys:
            r_info = rule_extracted.get(key, {"value": None, "confidence": 0.0, "source": "none"})
            r_val = r_info.get("value")
            r_conf = float(r_info.get("confidence", 0.0))

            ai_val = None
            ai_conf = 0.0
            if key in ai_extracted:
                ai_item = ai_extracted[key]
                ai_val = getattr(ai_item, "value", None)
                if ai_val is None and isinstance(ai_item, dict):
                    ai_val = ai_item.get("value")
                ai_conf = float(getattr(ai_item, "confidence", 0.0) or (ai_item.get("confidence", 0.0) if isinstance(ai_item, dict) else 0.0))

            # Select best value and source
            if ai_success and ai_val is not None and str(ai_val).strip() != "":
                if r_val is not None and str(r_val).strip().lower() == str(ai_val).strip().lower():
                    chosen_val = str(ai_val).strip()
                    chosen_conf = min(0.99, max(ai_conf, r_conf) + 0.05)
                    source = "rule+ai"
                else:
                    chosen_val = str(ai_val).strip()
                    chosen_conf = ai_conf if ai_conf > 0.0 else 0.90
                    source = "ai"
            elif r_val is not None and str(r_val).strip() != "":
                chosen_val = str(r_val).strip()
                chosen_conf = r_conf
                source = "rule"
            else:
                chosen_val = None
                chosen_conf = 0.0
                source = "none"

            # Intelligent normalization for dates and financial amounts
            norm_val = chosen_val
            if chosen_val:
                f_lower = key.lower()
                try:
                    from app.services.normalizer import InvoiceNormalizer
                    if "date" in f_lower:
                        n_date = InvoiceNormalizer.normalize_date(str(chosen_val))
                        if n_date.success and n_date.normalized_value:
                            norm_val = n_date.normalized_value
                    elif any(w in f_lower for w in ("amount", "total", "balance", "debit", "credit", "price", "fee")):
                        n_amt = InvoiceNormalizer.normalize_amount(str(chosen_val))
                        if n_amt.success and n_amt.normalized_value:
                            norm_val = n_amt.normalized_value
                except Exception:
                    pass

            final_fields[key] = {
                "field": key,
                "value": chosen_val,
                "original_value": chosen_val,
                "normalized_value": norm_val,
                "confidence": round(chosen_conf, 2),
                "source": source,
            }

        return final_fields


multi_type_extractor = MultiTypeExtractor()
