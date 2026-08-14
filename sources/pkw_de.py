"""
PKW.de Source Adapter

Queries the undocumented-but-public PKW.de REST API that the browser SPA
uses when rendering search results and vehicle detail pages.

SEARCH:  GET https://www.pkw.de/api/v1/cars/search/basic
DETAIL:  GET https://www.pkw.de/api/v1/cars/<listing_id>

Both endpoints:
- return JSON
- require no authentication
- require no cookies
- require no browser token

No scraping, no browser automation.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import config

from .base import (
    DiscoveredListing,
    DiscoveryRequest,
    PluginDescriptor,
    SourceAdapter,
    SourceCapabilities,
    SourceContext,
    SourceDescriptor,
    SourceListingDetail,
    SourceSnapshot,
)

# Public API base – same origin as the PKW.de website
_API_BASE = "https://www.pkw.de/api/v1"
_SEARCH_ENDPOINT = f"{_API_BASE}/cars/search/basic"
_DETAIL_ENDPOINT = f"{_API_BASE}/cars"

# Default search parameters for Audi A5 Cabriolet
_DEFAULT_SEARCH_PARAMS: dict[str, Any] = {
    "brand_model": "6_992",  # Audi (6) / A5 (992)
    "bodytype": 2,           # Cabriolet/Roadster
}

_DETAIL_URL_TEMPLATE = "https://suche.pkw.de/fahrzeuge/details/{listing_id}"

_DEFAULT_TIMEOUT = 30
_MAX_PAGES_SAFETY_CAP = 200  # hard safety cap – never exceed regardless of config

# IDs found in extras[] that indicate all-wheel drive
_AWD_EXTRA_IDS = frozenset({3})   # id=3 "Allradantrieb" in PKW.de extras taxonomy
_AWD_EXTRA_NAMES = frozenset({"allradantrieb", "quattro", "4matic", "xdrive", "awd", "4x4"})


class PkwDeAPIClient:
    """
    Thin HTTP client for the PKW.de public JSON API.

    Allows dependency injection in tests via the constructor.
    """

    def __init__(self, timeout: int = _DEFAULT_TIMEOUT):
        self.timeout = timeout

    def get_json(
        self, url: str, params: Optional[Mapping[str, Any]] = None
    ) -> Optional[dict]:
        query = ("?" + urlencode(params)) if params else ""
        full_url = url + query
        req = Request(
            full_url,
            headers={
                "Accept": "application/json",
                "User-Agent": (
                    "Mozilla/5.0 (compatible; CarHunter/3.0; "
                    "+https://github.com/networkerict/carhunter)"
                ),
            },
        )
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                if resp.status != 200:
                    raise PkwDeAPIError(
                        f"PKW.de API returned HTTP {resp.status} for {full_url}"
                    )
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except HTTPError as exc:
            raise PkwDeAPIError(
                f"PKW.de HTTP error {exc.code} for {full_url}"
            ) from exc
        except URLError as exc:
            raise PkwDeAPIError(
                f"PKW.de connection error for {full_url}: {exc.reason}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise PkwDeAPIError(
                f"PKW.de invalid JSON from {full_url}: {exc}"
            ) from exc


@dataclass
class PkwDeSourceAdapter(SourceAdapter):
    """
    PKW.de requests-only source adapter.

    Uses the same public JSON REST API that the pkw.de browser SPA uses.
    No credentials, no cookies, no browser required.
    """

    max_pages: int = field(
        default_factory=lambda: config.SOURCE_REGISTRY.get("pkw_de", {}).get(
            "max_pages", _MAX_PAGES_SAFETY_CAP
        )
    )
    search_params: dict[str, Any] = field(
        default_factory=lambda: dict(_DEFAULT_SEARCH_PARAMS)
    )
    api_client: Optional[PkwDeAPIClient] = field(default=None)

    def __post_init__(self):
        if self.api_client is None:
            object.__setattr__(self, "api_client", PkwDeAPIClient())

    # ------------------------------------------------------------------
    # SourceAdapter protocol
    # ------------------------------------------------------------------

    def descriptor(self) -> SourceDescriptor:
        plugin_descriptor = PluginDescriptor(
            plugin_id="pkw_de",
            plugin_family="source",
            plugin_version=config.VERSION,
            contract_version="1.0",
            display_name="PKW.de",
            capabilities=(
                "listing_discovery",
                "listing_detail",
                "full_inventory_scan",
                "structured_options",
            ),
            configuration_contract={
                "required": [],
                "optional": ["enabled", "max_pages"],
            },
        )
        return SourceDescriptor(
            source_name="pkw_de",
            display_name="PKW.de",
            version=config.VERSION,
            base_url="https://www.pkw.de",
            plugin_descriptor=plugin_descriptor,
        )

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            supports_listing_discovery=True,
            supports_detail_fetch=True,
            supports_description_fetch=False,  # description returned in detail JSON
            supports_full_inventory_scan=True,
            supports_structured_options=True,
        )

    def discover_listings(
        self, request: DiscoveryRequest, context: SourceContext
    ) -> list[DiscoveredListing]:
        max_pages = min(
            request.max_pages or self.max_pages,
            _MAX_PAGES_SAFETY_CAP,
        )
        discovered_at = datetime.now()
        listings: list[DiscoveredListing] = []
        seen_ids: set[str] = set()

        for page in range(1, max_pages + 1):
            params: dict[str, Any] = {**self.search_params, "page": page}

            try:
                response = self.api_client.get_json(_SEARCH_ENDPOINT, params)
            except PkwDeAPIError as exc:
                raise PkwDeAPIError(
                    f"PKW.de search failed on page {page}: {exc}"
                ) from exc

            if not response:
                break

            results = response.get("results", [])
            if not results:
                break

            for raw in results:
                try:
                    listing_id = str(raw.get("id") or "")
                    if not listing_id:
                        continue
                    if listing_id in seen_ids:
                        continue
                    seen_ids.add(listing_id)

                    source_url = _DETAIL_URL_TEMPLATE.format(listing_id=listing_id)
                    payload = deepcopy(raw)
                    payload["_pkw_page"] = page

                    listings.append(
                        DiscoveredListing(
                            source_name=context.source_name,
                            source_listing_id=listing_id,
                            source_url=source_url,
                            discovered_at=discovered_at,
                            raw_summary_payload=payload,
                        )
                    )
                except Exception:
                    # Malformed listing – skip and continue
                    continue

            # Respect pagination metadata
            pagination = response.get("total", {})
            total_pages = pagination.get("pages", 0) if isinstance(pagination, dict) else 0
            if total_pages and page >= total_pages:
                break

        return listings

    def fetch_listing_detail(
        self, listing: DiscoveredListing, context: SourceContext
    ) -> Optional[SourceListingDetail]:
        listing_id = listing.source_listing_id
        if not listing_id:
            return None

        url = f"{_DETAIL_ENDPOINT}/{listing_id}"
        try:
            data = self.api_client.get_json(url)
        except PkwDeAPIError:
            # Detail failure is non-fatal; snapshot still produced from summary
            return None

        if not data:
            return None

        return SourceListingDetail(
            source_name=context.source_name,
            source_listing_id=listing_id,
            fetched_at=datetime.now(),
            raw_detail_payload=deepcopy(data),
        )

    def fetch_description(
        self, listing: DiscoveredListing, context: SourceContext
    ) -> Optional[str]:
        # Description is included in the detail payload; no separate fetch needed.
        return None

    def to_source_snapshot(
        self,
        listing: DiscoveredListing,
        detail: Optional[SourceListingDetail] = None,
        description: Optional[str] = None,
    ) -> SourceSnapshot:
        raw_summary = listing.raw_summary_payload
        raw_detail = detail.raw_detail_payload if detail else None
        fetched_at = detail.fetched_at if detail else None

        # Prefer detail payload for enriched fields; fall back to summary
        merged = dict(raw_summary)
        if raw_detail:
            merged.update(raw_detail)

        extracted = self._extract_fields(merged)

        # description from detail payload (HTML – preserve as-is)
        desc = raw_detail.get("description") if raw_detail else None
        if desc:
            extracted["description"] = _strip_html_tags(desc)

        field_provenance = self._build_provenance(
            extracted_fields=extracted,
            source_listing_id=listing.source_listing_id,
            has_detail=(raw_detail is not None),
        )

        return SourceSnapshot(
            source_name=listing.source_name,
            source_listing_id=listing.source_listing_id,
            source_url=listing.source_url,
            discovered_at=listing.discovered_at,
            fetched_at=fetched_at,
            raw_summary_payload=deepcopy(raw_summary),
            raw_detail_payload=deepcopy(raw_detail) if raw_detail else None,
            extracted_fields=extracted,
            field_provenance=field_provenance,
        )

    # ------------------------------------------------------------------
    # Field extraction
    # ------------------------------------------------------------------

    def _extract_fields(self, merged: dict) -> dict:
        extracted: dict[str, Any] = {}

        # --- Identity ---
        listing_id = str(merged.get("id") or "")
        if listing_id:
            extracted["source_listing_id"] = listing_id

        # --- Title (name field) ---
        name = merged.get("name") or ""
        if name:
            extracted["title"] = name

        # --- Make ---
        brand = merged.get("brand") or {}
        if isinstance(brand, dict):
            make = brand.get("name") or ""
        else:
            make = str(brand)
        if make:
            extracted["make"] = make

        # --- Model ---
        model_obj = merged.get("model") or {}
        if isinstance(model_obj, dict):
            model_name = model_obj.get("name") or ""
        else:
            model_name = str(model_obj)
        if model_name:
            extracted["model"] = model_name

        # --- Body type ---
        bodytype = merged.get("bodytype") or {}
        if isinstance(bodytype, dict):
            bt_name = bodytype.get("name") or bodytype.get("id_and_name") or ""
        else:
            bt_name = str(bodytype)
        if bt_name:
            extracted["body_type"] = bt_name

        # --- First registration ---
        reg = merged.get("initial_registration") or ""
        if reg:
            extracted["first_registration"] = reg
            year = _parse_year(reg)
            if year:
                extracted["year"] = year

        # --- Mileage ---
        mileage = merged.get("mileage")
        if mileage is not None:
            try:
                extracted["mileage"] = int(mileage)
            except (ValueError, TypeError):
                pass

        # --- Price (customer listing price) ---
        price_obj = merged.get("price") or {}
        if isinstance(price_obj, dict):
            customer_price = price_obj.get("customer")
            if customer_price is not None:
                try:
                    extracted["price"] = int(round(float(customer_price)))
                except (ValueError, TypeError):
                    pass

        # --- Fuel ---
        fueltype = merged.get("fueltype") or {}
        if isinstance(fueltype, dict):
            fuel = fueltype.get("name") or ""
        else:
            fuel = str(fueltype)
        if fuel:
            extracted["fuel"] = fuel

        # --- Transmission ---
        geartype = merged.get("geartype") or {}
        if isinstance(geartype, dict):
            gear = geartype.get("name") or ""
        else:
            gear = str(geartype)
        if gear:
            extracted["transmission"] = gear

        # --- Power ---
        power_obj = merged.get("power") or {}
        if isinstance(power_obj, dict):
            kw = power_obj.get("kw")
            hp = power_obj.get("hp")
            if kw is not None:
                try:
                    extracted["power_kw"] = int(kw)
                except (ValueError, TypeError):
                    pass
            if hp is not None:
                try:
                    extracted["power_hp"] = int(hp)
                except (ValueError, TypeError):
                    pass

        # --- Colour ---
        color_obj = merged.get("color") or {}
        if isinstance(color_obj, dict):
            ext = color_obj.get("exterior") or {}
            int_ = color_obj.get("interior") or {}
            if isinstance(ext, dict):
                ext_name = ext.get("name") or ext.get("id_and_name") or ""
            else:
                ext_name = str(ext)
            if isinstance(int_, dict):
                int_name = int_.get("name") or int_.get("id_and_name") or ""
            else:
                int_name = str(int_)
            if ext_name:
                extracted["colour"] = ext_name
            if int_name:
                extracted["interior_colour"] = int_name

        # --- Dealer / seller ---
        owner = merged.get("owner") or {}
        if isinstance(owner, dict):
            dealer_name = owner.get("name") or ""
            dealer_type = owner.get("type") or ""
            dealer_phone = owner.get("phone") or ""
            if dealer_name:
                extracted["seller_name"] = dealer_name
            if dealer_type:
                extracted["seller_type"] = dealer_type
            if dealer_phone:
                extracted["seller_phone"] = dealer_phone

        # --- Location ---
        location = merged.get("location") or {}
        if isinstance(location, dict):
            city = location.get("city") or ""
            zip_code = location.get("zip") or ""
            country = location.get("country") or ""
            coords = location.get("coordinates") or {}
            if city:
                extracted["location_city"] = city
            if zip_code:
                extracted["location_zip"] = zip_code
            if country:
                extracted["location_country"] = country
            if isinstance(coords, dict):
                lat = coords.get("lat")
                lon = coords.get("lon")
                if lat is not None:
                    try:
                        extracted["location_lat"] = float(lat)
                    except (ValueError, TypeError):
                        pass
                if lon is not None:
                    try:
                        extracted["location_lon"] = float(lon)
                    except (ValueError, TypeError):
                        pass

        # --- Options / equipment (extras list) ---
        extras = merged.get("extras") or []
        if isinstance(extras, list) and extras:
            extracted["options"] = [
                e.get("name") or ""
                for e in extras
                if isinstance(e, dict) and e.get("name")
            ]
            extracted["options_raw"] = list(extras)

        # --- Drivetrain from extras ---
        drivetrain = _infer_drivetrain_from_extras(extras)
        if drivetrain:
            extracted["drivetrain"] = drivetrain

        # --- Availability ---
        extracted["availability"] = _map_availability(merged)

        # --- Source URL ---
        listing_id_str = str(merged.get("id") or "")
        if listing_id_str:
            extracted["source_url"] = _DETAIL_URL_TEMPLATE.format(
                listing_id=listing_id_str
            )

        # --- Images ---
        images = merged.get("images") or []
        if isinstance(images, list) and images:
            extracted["images"] = [
                img.get("full") or img.get("original") or img.get("thumb") or ""
                for img in images
                if isinstance(img, dict)
            ]

        return extracted

    def _build_provenance(
        self,
        *,
        extracted_fields: Mapping[str, Any],
        source_listing_id: str,
        has_detail: bool,
    ) -> dict[str, dict[str, Any]]:
        stage_map = {
            "description": "detail",
            "options": "detail",
            "options_raw": "detail",
            "images": "detail",
            "drivetrain": "detail",
        }
        provenance: dict[str, dict[str, Any]] = {}
        for field_name in extracted_fields:
            stage = stage_map.get(field_name, "summary")
            if stage == "detail" and not has_detail:
                stage = "summary"
            provenance[field_name] = {
                "source_name": "pkw_de",
                "source_listing_id": source_listing_id,
                "stage": stage,
            }
        return provenance


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_year(reg: str) -> Optional[int]:
    """Extract 4-digit year from ISO date string like '2022-07-01'."""
    if not reg:
        return None
    m = re.match(r"(\d{4})", str(reg).strip())
    if m:
        return int(m.group(1))
    return None


def _infer_drivetrain_from_extras(extras: list) -> Optional[str]:
    """Return 'AWD' if known AWD extra IDs or names are present, else None."""
    if not extras:
        return None
    for extra in extras:
        if not isinstance(extra, dict):
            continue
        if extra.get("id") in _AWD_EXTRA_IDS:
            return "AWD"
        name = (extra.get("name") or "").lower()
        if name in _AWD_EXTRA_NAMES:
            return "AWD"
    return None


def _map_availability(merged: dict) -> str:
    """
    Map PKW.de availability fields to canonical vocabulary:
    ACTIVE | INACTIVE | SOLD | UNKNOWN

    PKW.de does not expose an explicit sold flag in the public API.
    We only mark ACTIVE if the listing data looks live.
    """
    deleted = merged.get("deleted")
    if deleted is True:
        return "INACTIVE"
    available_online = merged.get("available_online")
    # Most listings will have available_online = False (standard dealer listings)
    # We treat presence of a listing record as ACTIVE unless explicitly deleted.
    return "ACTIVE"


def _strip_html_tags(text: str) -> str:
    """Remove HTML tags from description text."""
    return re.sub(r"<[^>]+>", "", text or "").strip()


# ------------------------------------------------------------------
# Errors
# ------------------------------------------------------------------

class PkwDeAPIError(Exception):
    """Raised when the PKW.de API request fails."""
