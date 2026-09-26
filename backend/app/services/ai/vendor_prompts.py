"""
Vendor-specific prompt management registry.
Maintains modular, independent vendor-specific extraction instructions that can be
updated or migrated to PostgreSQL in the future without changing LLM provider code.
"""

import re
from typing import Dict, List, Optional

# In-memory vendor prompt registry
# Designed for clean future database migration (e.g. PostgreSQL `vendor_prompt_configs` table)
VENDOR_PROMPTS: Dict[str, Dict[str, str]] = {
    "abc_suppliers": {
        "vendor_name": "ABC Suppliers",
        "prompt": (
            "Vendor-specific instructions for ABC Suppliers:\n"
            "- Invoice number usually appears after or near 'Inv No'.\n"
            "- Invoice date usually appears after or near 'Invoice Dt'.\n"
            "- Final payable amount usually appears after or near 'Net Payable'.\n"
            "- Ignore PO Number when identifying invoice number.\n"
            "- Prefer the seller/vendor name appearing in the invoice header."
        ),
    },
}


def normalize_vendor_key(key: Optional[str]) -> str:
    """
    Normalizes a vendor name or identifier into a canonical lookup key.
    Converts to lowercase, removes punctuation, and replaces spaces with underscores.
    """
    if not key or not isinstance(key, str):
        return ""
    cleaned = key.strip().lower()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", "_", cleaned).strip("_")
    return cleaned


def get_vendor_prompt(vendor_id_or_name: Optional[str]) -> Optional[Dict[str, str]]:
    """
    Looks up vendor-specific extraction prompt configuration.

    Search strategy:
    1. Direct key match (e.g. 'abc_suppliers')
    2. Normalized key match
    3. Exact or case-insensitive match against registered vendor_name field
    4. Fuzzy/substring match between normalized vendor name and keys

    Returns:
        Dict with 'prompt' and 'vendor_name' if found, else None.
    """
    if not vendor_id_or_name or not isinstance(vendor_id_or_name, str):
        return None

    raw_key = vendor_id_or_name.strip()
    norm_key = normalize_vendor_key(raw_key)
    if not norm_key:
        return None

    # 1. Direct key match
    if raw_key in VENDOR_PROMPTS:
        return VENDOR_PROMPTS[raw_key]

    # 2. Normalized key match
    if norm_key in VENDOR_PROMPTS:
        return VENDOR_PROMPTS[norm_key]

    # 3. Match against vendor_name attribute
    for v_id, cfg in VENDOR_PROMPTS.items():
        v_name = cfg.get("vendor_name", "")
        if v_name.strip().lower() == raw_key.lower():
            return cfg
        if normalize_vendor_key(v_name) == norm_key:
            return cfg

    # 4. Substring containment match
    for v_id, cfg in VENDOR_PROMPTS.items():
        if v_id in norm_key or norm_key in v_id:
            return cfg
        v_name_norm = normalize_vendor_key(cfg.get("vendor_name", ""))
        if v_name_norm and (v_name_norm in norm_key or norm_key in v_name_norm):
            return cfg

    return None


def register_vendor_prompt(vendor_id: str, prompt_data: Dict[str, str]) -> None:
    """
    Registers or updates a vendor prompt configuration in the registry.
    Useful for testing and dynamic runtime configuration.
    """
    key = normalize_vendor_key(vendor_id) or vendor_id.strip()
    VENDOR_PROMPTS[key] = prompt_data


def unregister_vendor_prompt(vendor_id: str) -> None:
    """Removes a vendor prompt from the registry."""
    key = normalize_vendor_key(vendor_id) or vendor_id.strip()
    VENDOR_PROMPTS.pop(key, None)


def list_vendor_prompts() -> List[str]:
    """Returns all currently registered vendor IDs."""
    return list(VENDOR_PROMPTS.keys())
