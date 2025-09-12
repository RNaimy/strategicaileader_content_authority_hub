"""
Google Search Console client (service layer)

This module provides a thin wrapper around the Search Console API for
retrieving Search Analytics metrics and normalizing them into a
consistent structure the API layer can ingest.

Auth options supported:
- Service Account (recommended for servers): uses a JSON key file.
- OAuth User Consent (for local/dev): uses a client_secret.json file.
- OAuth refresh token (server-safe): use stored refresh token + client id/secret.

Notes
-----
* We try both discovery services: 'searchconsole' (v1) and legacy
  'webmasters' (v3) for compatibility. The resource/method we use is
  `searchanalytics().query` which exists on both.
* This module is import-safe even if Google client libs are not
  installed; it raises a friendly ImportError with guidance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import json
import logging

logger = logging.getLogger(__name__)

# Lazy/import-safe Google client imports
try:
    from google.oauth2.service_account import Credentials as SACredentials
    from google.auth.credentials import Credentials as BaseCredentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials as OAuthCredentials
    from google.auth.transport.requests import Request
except Exception as e:  # pragma: no cover - import guidance only
    SACredentials = None  # type: ignore
    BaseCredentials = object  # type: ignore
    InstalledAppFlow = None  # type: ignore
    build = None  # type: ignore
    OAuthCredentials = None  # type: ignore
    Request = None  # type: ignore
    _IMPORT_ERR = e
else:
    _IMPORT_ERR = None

# Official scope for Search Console data access
SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
]


@dataclass
class QueryResult:
    site_url: str
    start_date: str
    end_date: str
    dimensions: List[str]
    rows: List[Dict[str, Any]]
    totals: Dict[str, float]


class GSCClient:
    """Google Search Console API client wrapper.

    Usage:
        client = GSCClient.from_service_account("svc.json", subject="you@domain.com")
        data = client.query_site("https://www.strategicaileader.com/", date(2025,8,1), date(2025,8,27))
    """

    def __init__(self, creds: BaseCredentials):
        if _IMPORT_ERR is not None:
            raise ImportError(
                "Google API client libraries are not installed.\n"
                "Run: pip install google-api-python-client google-auth google-auth-oauthlib"
            ) from _IMPORT_ERR
        self._creds = creds
        self._service = None  # built lazily

    # -----------------------------
    # Auth constructors
    # -----------------------------
    @classmethod
    def from_service_account(
        cls,
        json_key_path: str,
        *,
        subject: Optional[str] = None,
        scopes: Optional[List[str]] = None,
    ) -> "GSCClient":
        if _IMPORT_ERR is not None:
            raise ImportError(
                "Google API client libraries are not installed.\n"
                "Run: pip install google-api-python-client google-auth google-auth-oauthlib"
            ) from _IMPORT_ERR
        scopes = scopes or SCOPES
        if SACredentials is None:  # pragma: no cover
            raise RuntimeError("google-auth is not available")
        creds = SACredentials.from_service_account_file(json_key_path, scopes=scopes)
        if subject:
            creds = creds.with_subject(subject)
        return cls(creds)

    @classmethod
    def from_oauth(
        cls, client_secret_path: str, *, scopes: Optional[List[str]] = None
    ) -> "GSCClient":
        if _IMPORT_ERR is not None:
            raise ImportError(
                "Google API client libraries are not installed.\n"
                "Run: pip install google-api-python-client google-auth google-auth-oauthlib"
            ) from _IMPORT_ERR
        if InstalledAppFlow is None:  # pragma: no cover
            raise RuntimeError("google-auth-oauthlib is not available")
        scopes = scopes or SCOPES
        flow = InstalledAppFlow.from_client_secrets_file(
            client_secret_path, scopes=scopes
        )
        creds = flow.run_local_server(port=0)
        return cls(creds)

    @classmethod
    def from_oauth_refresh_token(
        cls,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        *,
        scopes: Optional[List[str]] = None,
    ) -> "GSCClient":
        """Create client from a long-lived OAuth refresh token.

        Useful for server-side jobs once you've captured a user consent token.
        """
        if _IMPORT_ERR is not None:
            raise ImportError(
                "Google API client libraries are not installed.\n"
                "Run: pip install google-api-python-client google-auth google-auth-oauthlib"
            ) from _IMPORT_ERR
        if OAuthCredentials is None:  # pragma: no cover
            raise RuntimeError("google-auth is not available")
        scopes = scopes or SCOPES
        creds = OAuthCredentials(
            None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes,
        )
        # Force a refresh so we fail fast if secrets are wrong
        if Request is None:  # pragma: no cover
            raise RuntimeError("google-auth transport is not available")
        creds.refresh(Request())
        return cls(creds)

    # -----------------------------
    # Core API
    # -----------------------------
    def _get_service(self):
        if self._service is not None:
            return self._service
        assert build is not None  # for type checkers

        # Try new discovery name first, then legacy fallback
        last_err: Optional[Exception] = None
        for api, ver in (("searchconsole", "v1"), ("webmasters", "v3")):
            try:
                svc = build(api, ver, credentials=self._creds, cache_discovery=False)
                # Smoke call: verify resource(s) are present
                getattr(svc, "searchanalytics")
                self._service = svc
                logger.info("Initialized GSC service using %s %s", api, ver)
                return self._service
            except Exception as e:  # pragma: no cover - env dependent
                last_err = e
                logger.debug("Failed to init %s %s: %s", api, ver, e)
        # If we reached here, both attempts failed
        raise RuntimeError(f"Unable to initialize Search Console API: {last_err}")

    @staticmethod
    def _normalize_site_url(site_url: str) -> str:
        s = site_url.strip()
        if not (s.startswith("http://") or s.startswith("https://")):
            s = "https://" + s.strip("/") + "/"
        if not s.endswith("/"):
            s += "/"
        return s

    def query_site(
        self,
        site_url: str,
        start: date,
        end: date,
        *,
        dimensions: Optional[List[str]] = None,
        row_limit: int = 25000,
        start_row: int = 0,
        dimension_filter_groups: Optional[List[Dict[str, Any]]] = None,
        data_state: str = "final",  # or "all"
    ) -> QueryResult:
        """Run a Search Analytics query for a property.

        Returns a QueryResult with raw rows and totals. Each row is a dict:
            {"keys": [dim1, dim2, ...], "clicks": ..., "impressions": ..., "ctr": ..., "position": ...}
        """
        service = self._get_service()
        site = self._normalize_site_url(site_url)
        dims = dimensions or ["page"]

        body: Dict[str, Any] = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": dims,
            "rowLimit": row_limit,
            "startRow": start_row,
            "dataState": data_state,
        }
        if dimension_filter_groups:
            body["dimensionFilterGroups"] = dimension_filter_groups

        # Call whichever discovery name succeeded
        resource = getattr(service, "searchanalytics")()
        resp = resource.query(siteUrl=site, body=body).execute()

        rows: List[Dict[str, Any]] = resp.get("rows", [])
        totals = {
            "clicks": float(resp.get("totalClicks", 0) or 0),
            "impressions": float(resp.get("totalImpressions", 0) or 0),
            "ctr": float(resp.get("averageCtr", 0) or 0),
            "position": float(resp.get("averagePosition", 0) or 0),
        }

        return QueryResult(
            site_url=site,
            start_date=body["startDate"],
            end_date=body["endDate"],
            dimensions=dims,
            rows=rows,
            totals=totals,
        )

    def list_sites(self) -> List[Dict[str, Any]]:
        """Return the list of sites the authenticated principal has access to.

        Uses whichever discovery name succeeded (searchconsole or webmasters).
        """
        service = self._get_service()
        # both APIs expose `sites().list()`
        sites_resource = getattr(service, "sites")()
        resp = sites_resource.list().execute()
        return resp.get("siteEntry", []) or resp.get("siteEntry", [])

    def has_access_to(self, site_url: str) -> bool:
        """Best-effort check whether the principal can access `site_url`."""
        norm = self._normalize_site_url(site_url)
        try:
            entries = self.list_sites()
        except Exception:  # pragma: no cover - remote dependent
            return True  # don't block queries purely on this check
        for e in entries or []:
            if (e.get("siteUrl") or "").rstrip("/") + "/" == norm:
                # Optional: verify permission level if present
                perm = (e.get("permissionLevel") or "").lower()
                if perm and perm not in {"siteunverifieduser", "none"}:
                    return True
                # If no permission field, assume OK if listed
                return True
        return False

    # -----------------------------
    # Helpers
    # -----------------------------
    @staticmethod
    def summarize_totals(rows: List[Dict[str, Any]]) -> Dict[str, float]:
        clicks = sum(float(r.get("clicks", 0) or 0) for r in rows)
        impressions = sum(float(r.get("impressions", 0) or 0) for r in rows)
        ctr = (clicks / impressions) if impressions else 0.0
        # average of averages is not perfect; weighted could be added later
        positions = [
            float(r.get("position", 0) or 0)
            for r in rows
            if r.get("position") is not None
        ]
        position = (sum(positions) / len(positions)) if positions else 0.0
        return {
            "clicks": clicks,
            "impressions": impressions,
            "ctr": ctr,
            "position": position,
        }


# Convenience function to quickly test with env vars (optional)
def quick_demo_from_service_account(
    json_key_path: str,
    site_url: str,
    start: date,
    end: date,
    *,
    subject: Optional[str] = None,
    dimensions: Optional[List[str]] = None,
) -> Tuple[QueryResult, Dict[str, float]]:
    client = GSCClient.from_service_account(json_key_path, subject=subject)
    res = client.query_site(site_url, start, end, dimensions=dimensions)
    return res, GSCClient.summarize_totals(res.rows)


def quick_demo_from_oauth_refresh(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    site_url: str,
    start: date,
    end: date,
    *,
    dimensions: Optional[List[str]] = None,
) -> Tuple[QueryResult, Dict[str, float]]:
    client = GSCClient.from_oauth_refresh_token(client_id, client_secret, refresh_token)
    res = client.query_site(site_url, start, end, dimensions=dimensions)
    return res, GSCClient.summarize_totals(res.rows)
