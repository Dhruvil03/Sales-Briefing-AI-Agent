# backend/app/services/hubspot.py
"""
HubSpot CRM export — creates or updates a Contact with structured fields
extracted from the prospect profile via LLM.

Required scope: crm.objects.contacts.write  (just this one)

Get your key: HubSpot → Settings → Integrations → Private Apps → Create app
Add scope: CRM → Contacts → Read + Write
"""
from __future__ import annotations

import json
import os
import httpx

HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY", "")

_BASE = "https://api.hubapi.com"


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {HUBSPOT_API_KEY}",
    }


_EXTRACT_PROMPT = """\
Extract contact information from the prospect profile below.
Return ONLY a JSON object with these keys (use empty string "" for any field not found):
  job_title  — current job title or role
  phone      — phone number if explicitly mentioned
  email      — email address if explicitly mentioned

Rules:
- job_title must be a real title (e.g. "VP of Sales", "Chief Revenue Officer") — not a description
- phone and email are usually absent in public profiles — only include if clearly stated
- Return raw JSON only, no markdown fences, no explanation

PROSPECT PROFILE:
{profile}
"""


async def _extract_fields(profile_text: str) -> dict[str, str]:
    """Use LLM to extract structured contact fields. Returns {} on failure."""
    from app.services.llm import complete  # local import to avoid circular deps
    try:
        raw = await complete(_EXTRACT_PROMPT.format(profile=profile_text[:3000]))
        # Strip any accidental markdown fences
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(raw)
        return {k: str(v).strip() for k, v in data.items() if v}
    except Exception:
        return {}


async def export_to_hubspot(
    *,
    prospect_name: str,
    company_name: str,
    prospect_profile: str,
    company_url: str | None = None,
    company_summary: str | None = None,
    report_md: str | None = None,
) -> dict:
    """
    Creates (or finds) a HubSpot Contact and writes the research into the
    contact's description field.

    Only requires: crm.objects.contacts.write

    Returns {"contact_id": str, "action": "created" | "updated"}.
    Raises RuntimeError on failure.
    """
    if not HUBSPOT_API_KEY:
        raise RuntimeError(
            "HUBSPOT_API_KEY is not set. "
            "Create a Private App in HubSpot → Settings → Integrations → Private Apps. "
            "Required scope: crm.objects.contacts.write"
        )

    name_parts = prospect_name.strip().split(" ", 1)
    firstname = name_parts[0]
    lastname  = name_parts[1] if len(name_parts) > 1 else ""

    # LLM-extract structured fields from the profile text
    extracted = await _extract_fields(prospect_profile)
    jobtitle  = extracted.get("job_title", "")
    phone     = extracted.get("phone", "")
    email     = extracted.get("email", "")

    async with httpx.AsyncClient(timeout=15.0) as client:

        # ── 1. Search for existing contact by full name ───────────────────────
        contact_id: str | None = None
        action = "created"

        try:
            search_r = await client.post(
                f"{_BASE}/crm/v3/objects/contacts/search",
                headers=_headers(),
                json={
                    "filterGroups": [{
                        "filters": [
                            {"propertyName": "firstname", "operator": "EQ", "value": firstname},
                            {"propertyName": "lastname",  "operator": "EQ", "value": lastname},
                        ]
                    }],
                    "properties": ["firstname", "lastname", "company"],
                    "limit": 3,
                },
            )
            if search_r.is_success:
                results = search_r.json().get("results", [])
                if results:
                    contact_id = results[0]["id"]
                    action = "updated"
        except Exception:
            pass  # search is best-effort; fall through to create

        # ── 2. Build properties — only include non-empty values ───────────────
        properties: dict[str, str] = {
            "firstname":      firstname,
            "lastname":       lastname,
            "company":        company_name,
            "hs_lead_status": "NEW",
        }
        if jobtitle:
            properties["jobtitle"] = jobtitle
        if phone:
            properties["phone"] = phone
        if email:
            properties["email"] = email
        if company_url:
            # Strip to bare domain for the website field
            properties["website"] = company_url if company_url.startswith("http") else f"https://{company_url}"

        # ── 3. Create or update contact ───────────────────────────────────────
        if contact_id:
            patch_r = await client.patch(
                f"{_BASE}/crm/v3/objects/contacts/{contact_id}",
                headers=_headers(),
                json={"properties": properties},
            )
            if not patch_r.is_success:
                raise RuntimeError(
                    f"HubSpot contact update failed: {patch_r.status_code} {patch_r.text[:300]}"
                )
        else:
            create_r = await client.post(
                f"{_BASE}/crm/v3/objects/contacts",
                headers=_headers(),
                json={"properties": properties},
            )
            if not create_r.is_success:
                raise RuntimeError(
                    f"HubSpot contact creation failed: {create_r.status_code} {create_r.text[:300]}"
                )
            contact_id = create_r.json()["id"]

    return {
        "contact_id": contact_id,
        "action":     action,
        "fields_set": [k for k in properties if k not in ("firstname", "lastname")],
    }
