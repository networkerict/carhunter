"""
Mobile.de Search API Adapter

This adapter implements the official Mobile.de Search API integration.

Official API Documentation:
- https://services.mobile.de/docs/search-api.html
- https://services.mobile.de/manual/index.html

The adapter:
- Uses HTTP Basic Authentication (credentials via environment/config)
- Queries the official Mobile.de Search API endpoint
- Parses JSON responses into SourceSnapshot objects
- Preserves mobileAdId, detailPageUrl, seller info, pricing, vehicle data
- Handles pagination, errors, and malformed responses
- Does NOT scrape, does NOT use undocumented endpoints

Production use requires:
- Mobile.de API account (contact Mobile.de support for activation)
- Valid API credentials (MOBILE_DE_API_USERNAME, MOBILE_DE_API_PASSWORD)
- Understanding of Mobile.de data usage terms
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

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


# Official Mobile.de Search API endpoint
MOBILE_DE_API_BASE = "https://services.mobile.de/search-api"
SEARCH_ENDPOINT = f"{MOBILE_DE_API_BASE}/searches/used-cars"
AD_DETAIL_ENDPOINT = f"{MOBILE_DE_API_BASE}/ad"

# Acceptable pagination limits
MAX_PAGE_SIZE = 100
MAX_PAGES_DEFAULT = 10
TIMEOUT_SECONDS = 30


class MobileDeAPIClient:
    """
    HTTP client for Mobile.de official Search API.
    
    Handles:
    - HTTP Basic Authentication
    - JSON request/response
    - Error handling
    - Timeout management
    - Credential injection from environment
    
    Allows dependency injection for testing with mock responses.
    """

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = TIMEOUT_SECONDS,
    ):
        """
        Initialize API client with credentials.

        Args:
            username: API username (from environment if not provided)
            password: API password (from environment if not provided)
            timeout: HTTP request timeout in seconds
        """
        self.username = username or os.environ.get("MOBILE_DE_API_USERNAME", "")
        self.password = password or os.environ.get("MOBILE_DE_API_PASSWORD", "")
        self.timeout = timeout
        self._credentials_available = bool(self.username and self.password)

    def _build_auth_header(self) -> str:
        """Build HTTP Basic Auth header."""
        if not self.username or not self.password:
            return ""
        credentials = f"{self.username}:{self.password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def get_json(self, url: str, params: Optional[Mapping[str, Any]] = None) -> Optional[Mapping[str, Any]]:
        """
        Make HTTP GET request, return parsed JSON.

        Args:
            url: Base URL
            params: Query parameters dict

        Returns:
            Parsed JSON dict or None on error

        Raises:
            HTTPError, URLError, json.JSONDecodeError for errors
        """
        query_string = ""
        if params:
            query_string = "?" + urlencode(params)

        full_url = url + query_string
        auth_header = self._build_auth_header()

        req = Request(full_url)
        req.add_header("Accept", "application/vnd.de.mobil.api+json")
        if auth_header:
            req.add_header("Authorization", auth_header)

        try:
            with urlopen(req, timeout=self.timeout) as response:
                data = response.read().decode("utf-8")
                return json.loads(data)
        except (HTTPError, URLError) as e:
            # Re-raise with context
            raise e
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response from {url}: {e}")

    def credentials_available(self) -> bool:
        """Check if API credentials are configured."""
        return self._credentials_available


@dataclass
class MobileDeSourceAdapter(SourceAdapter):
    """
    Official Mobile.de Search API adapter.

    This adapter queries the official Mobile.de Search API endpoint and
    produces SourceSnapshot objects compatible with CarHunter's canonical
    domain model.

    No scraping is used. All data comes from the official documented API.

    Production credentials are NOT included. They must be provided via:
    - MOBILE_DE_API_USERNAME environment variable
    - MOBILE_DE_API_PASSWORD environment variable

    For testing, mock credentials or fixture responses can be injected
    through the api_client parameter.
    """

    api_client: Optional[MobileDeAPIClient] = None
    max_pages: int = MAX_PAGES_DEFAULT
    page_size: int = 50

    def __post_init__(self):
        """Initialize API client if not provided."""
        if self.api_client is None:
            object.__setattr__(self, "api_client", MobileDeAPIClient())

    def descriptor(self) -> SourceDescriptor:
        """Describe this adapter."""
        plugin_descriptor = PluginDescriptor(
            plugin_id="mobile_de",
            plugin_family="source",
            plugin_version="1.0",
            contract_version="1.0",
            display_name="Mobile.de",
            capabilities=(
                "listing_discovery",
                "listing_detail",
                "description_fetch",
                "full_inventory_scan",
            ),
            configuration_contract={
                "required": [],
                "optional": ["enabled", "max_pages", "page_size"],
            },
        )
        return SourceDescriptor(
            source_name="mobile_de",
            display_name="Mobile.de",
            version="1.0",
            base_url="https://www.mobile.de",
            plugin_descriptor=plugin_descriptor,
        )

    def capabilities(self) -> SourceCapabilities:
        """Report capabilities."""
        return SourceCapabilities(
            supports_listing_discovery=True,
            supports_detail_fetch=True,
            supports_description_fetch=True,
            supports_full_inventory_scan=True,
        )

    def discover_listings(
        self, request: DiscoveryRequest, context: SourceContext
    ) -> list[DiscoveredListing]:
        """
        Discover vehicle listings from Mobile.de API.

        Queries the official Search API endpoint with pagination.
        Each listing is converted to a DiscoveredListing object.

        Args:
            request: Discovery request (max_pages override)
            context: Source context (source name for provenance)

        Returns:
            List of DiscoveredListing objects
        """
        if not self.api_client.credentials_available():
            raise SourceCredentialsError(
                "Mobile.de API credentials not configured. "
                "Set MOBILE_DE_API_USERNAME and MOBILE_DE_API_PASSWORD."
            )

        discovered_at = datetime.now()
        listings = []
        max_pages = request.max_pages or self.max_pages

        # Query pagination loop
        for page in range(1, max_pages + 1):
            params = {
                "pageNumber": page,
                "pageSize": min(self.page_size, MAX_PAGE_SIZE),
            }

            try:
                response = self.api_client.get_json(SEARCH_ENDPOINT, params)
            except Exception as e:
                # Failure to fetch one page doesn't invalidate entire source
                # Log and return what we have so far
                raise SourceAPIError(
                    f"Mobile.de Search API error on page {page}: {e}"
                ) from e

            if not response:
                break

            # Parse search results
            ads = response.get("ads", [])
            if not ads:
                # Empty page = end of results
                break

            current_page = response.get("currentPage", page)
            max_pages_api = response.get("maxPages", 0)

            for ad in ads:
                try:
                    listing = self._parse_ad_listing(ad, discovered_at, context)
                    if listing:
                        listings.append(listing)
                except Exception as e:
                    # Malformed listing doesn't invalidate entire source
                    # Silently skip and continue
                    continue

            # Stop if we've reached the last page
            if current_page >= max_pages_api:
                break

        return listings

    def fetch_listing_detail(
        self, listing: DiscoveredListing, context: SourceContext
    ) -> Optional[SourceListingDetail]:
        """
        Fetch detailed listing information from Mobile.de API.

        Mobile.de Search API already returns most detail in the search results.
        This method can fetch additional data via the individual ad endpoint
        if needed, or return None if search results are sufficient.

        Args:
            listing: Discovered listing
            context: Source context

        Returns:
            SourceListingDetail or None
        """
        # Mobile.de Search API returns comprehensive data in search results.
        # For now, we use the search result as the detail.
        # If additional fields are needed, this would fetch from /ad/{ad-key}
        # endpoint.

        ad_id = listing.source_listing_id
        if not ad_id:
            return None

        try:
            params = {}
            response = self.api_client.get_json(f"{AD_DETAIL_ENDPOINT}/{ad_id}", params)
        except Exception as e:
            # Detail fetch failure doesn't block snapshot creation
            return None

        if not response:
            return None

        return SourceListingDetail(
            source_name=context.source_name,
            source_listing_id=ad_id,
            fetched_at=datetime.now(),
            raw_detail_payload=response,
        )

    def fetch_description(
        self, listing: DiscoveredListing, context: SourceContext
    ) -> Optional[str]:
        """
        Fetch listing description from Mobile.de API.

        Mobile.de provides plainTextDescription in search results.

        Args:
            listing: Discovered listing
            context: Source context

        Returns:
            Description text or None
        """
        raw = listing.raw_summary_payload
        return raw.get("plainTextDescription") or None

    def to_source_snapshot(
        self,
        listing: DiscoveredListing,
        detail: Optional[SourceListingDetail] = None,
        description: Optional[str] = None,
    ) -> SourceSnapshot:
        """
        Convert discovered listing to SourceSnapshot.

        Maps Mobile.de API fields to canonical CarHunter SourceSnapshot contract.

        Args:
            listing: Discovered listing
            detail: Optional detail response
            description: Optional description

        Returns:
            SourceSnapshot object
        """
        raw = listing.raw_summary_payload
        extracted = self._extract_fields(raw, description)

        return SourceSnapshot(
            source_name=listing.source_name,
            source_listing_id=listing.source_listing_id,
            source_url=listing.source_url,
            discovered_at=listing.discovered_at,
            fetched_at=detail.fetched_at if detail else None,
            raw_summary_payload=raw,
            raw_detail_payload=detail.raw_detail_payload if detail else None,
            extracted_fields=extracted,
            field_provenance=self._build_provenance(raw),
        )

    def _parse_ad_listing(
        self, ad: Mapping[str, Any], discovered_at: datetime, context: SourceContext
    ) -> Optional[DiscoveredListing]:
        """
        Parse a single ad from Mobile.de Search API response.

        Args:
            ad: Ad object from API response
            discovered_at: Discovery timestamp
            context: Source context

        Returns:
            DiscoveredListing or None if required fields are missing
        """
        # Extract required fields
        mobile_ad_id = ad.get("mobileAdId")
        if not mobile_ad_id:
            return None

        detail_url = ad.get("detailPageUrl")
        if not detail_url:
            # Construct URL if not provided
            detail_url = f"https://www.mobile.de/auto-inserat/{mobile_ad_id}.html"

        return DiscoveredListing(
            source_name=context.source_name,
            source_listing_id=str(mobile_ad_id),
            source_url=detail_url,
            discovered_at=discovered_at,
            raw_summary_payload=dict(ad),  # Preserve raw API response
        )

    def _extract_fields(
        self, raw: Mapping[str, Any], description: Optional[str] = None
    ) -> Mapping[str, Any]:
        """
        Extract normalized fields from Mobile.de API response.

        Maps Mobile.de fields to CarHunter canonical fields.
        Unknown fields are omitted (not fabricated).

        Args:
            raw: Raw API response object
            description: Optional description text

        Returns:
            Dict of extracted fields
        """
        extracted = {}

        # Vehicle identification
        if "make" in raw:
            extracted["make"] = raw["make"]
        if "model" in raw:
            extracted["model"] = raw["model"]
        if "modelDescription" in raw:
            extracted["model_variant"] = raw["modelDescription"]

        # Condition and registration
        if "condition" in raw:
            extracted["condition"] = raw["condition"]
        if "firstRegistration" in raw:
            # Format: "202007" -> extract year and month
            reg = raw["firstRegistration"]
            if isinstance(reg, str) and len(reg) >= 4:
                extracted["year"] = int(reg[:4])

        # Mileage
        if "mileage" in raw:
            mileage = raw.get("mileage")
            if isinstance(mileage, int):
                extracted["mileage"] = mileage

        # Fuel type
        if "fuel" in raw:
            extracted["fuel"] = raw["fuel"]

        # Body type/category
        if "category" in raw:
            extracted["body_type"] = raw["category"]

        # Pricing
        price_obj = raw.get("price", {})
        if isinstance(price_obj, dict):
            if "consumerPriceGross" in price_obj:
                try:
                    extracted["price_gross"] = float(price_obj["consumerPriceGross"])
                except (ValueError, TypeError):
                    pass
            if "currency" in price_obj:
                extracted["currency"] = price_obj["currency"]

        # Damage status
        if "damageUnrepaired" in raw:
            extracted["damage_unrepaired"] = raw["damageUnrepaired"]

        # Seller information
        seller_obj = raw.get("seller", {})
        if isinstance(seller_obj, dict):
            if "type" in seller_obj:
                extracted["seller_type"] = seller_obj["type"]
            if "commercial" in seller_obj:
                extracted["seller_commercial"] = seller_obj["commercial"]
            if "companyName" in seller_obj:
                extracted["seller_name"] = seller_obj["companyName"]
            if "email" in seller_obj:
                extracted["seller_email"] = seller_obj["email"]

            # Location
            address = seller_obj.get("address", {})
            if isinstance(address, dict):
                if "city" in address:
                    extracted["location_city"] = address["city"]
                if "zipcode" in address:
                    extracted["location_zipcode"] = address["zipcode"]
                if "country" in address:
                    extracted["location_country"] = address["country"]

            # Geo coordinates
            geo = seller_obj.get("geoData", {})
            if isinstance(geo, dict):
                if "lat" in geo:
                    extracted["location_lat"] = float(geo["lat"])
                if "lon" in geo:
                    extracted["location_lon"] = float(geo["lon"])

        # Description
        if description:
            extracted["description"] = description
        elif "plainTextDescription" in raw:
            extracted["description"] = raw["plainTextDescription"]

        # Timestamps
        if "creationDate" in raw:
            extracted["created_at"] = raw["creationDate"]
        if "modificationDate" in raw:
            extracted["modified_at"] = raw["modificationDate"]

        return extracted

    def _build_provenance(
        self, raw: Mapping[str, Any]
    ) -> Mapping[str, Mapping[str, Any]]:
        """
        Build field provenance tracking.

        Documents where each extracted field came from in the API response.

        Args:
            raw: Raw API response

        Returns:
            Dict mapping field names to their source information
        """
        return {
            "make": {"source": "mobile.de.api", "field": "make"},
            "model": {"source": "mobile.de.api", "field": "model"},
            "model_variant": {"source": "mobile.de.api", "field": "modelDescription"},
            "year": {"source": "mobile.de.api", "field": "firstRegistration", "transform": "extract_year"},
            "mileage": {"source": "mobile.de.api", "field": "mileage"},
            "fuel": {"source": "mobile.de.api", "field": "fuel"},
            "body_type": {"source": "mobile.de.api", "field": "category"},
            "price_gross": {"source": "mobile.de.api", "field": "price.consumerPriceGross"},
            "currency": {"source": "mobile.de.api", "field": "price.currency"},
            "seller_type": {"source": "mobile.de.api", "field": "seller.type"},
            "location_city": {"source": "mobile.de.api", "field": "seller.address.city"},
            "location_country": {"source": "mobile.de.api", "field": "seller.address.country"},
            "description": {"source": "mobile.de.api", "field": "plainTextDescription"},
        }


class SourceCredentialsError(Exception):
    """Raised when API credentials are missing or invalid."""
    pass


class SourceAPIError(Exception):
    """Raised when API request fails."""
    pass
