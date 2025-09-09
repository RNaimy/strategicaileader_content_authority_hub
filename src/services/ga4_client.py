from __future__ import annotations

import os
import re
import datetime as dt
from typing import Optional, Dict, Any

# NOTE: we import Google SDKs lazily inside methods so the app can run without
# these dependencies in non-analytics code paths or CI where they aren't needed.

class GA4ConfigError(RuntimeError):
    """Raised when required GA4 configuration is missing or invalid."""


class GA4Client:
    """
    Thin wrapper around Google Analytics Data API (GA4) supporting two auth modes:

    1) OAuth (recommended for user-owned properties):
       - GA4_CLIENT_ID
       - GA4_CLIENT_SECRET
       - GA4_REFRESH_TOKEN
       (optional) GA4_AUTH_METHOD=oauth

    2) Service Account JSON:
       - GA4_CREDENTIALS_JSON (path to key file)
       (optional) GA4_AUTH_METHOD=service_account

    Property selection:
      - Prefer explicit `property_id` param to `fetch_summary()`.
      - Else use env `GA4_PROPERTY_ID`.
      - Else, if exactly one env var matching `GA4_PROPERTY_ID_*` is set, use it.
      - Otherwise raise with a helpful message.
    """

    def __init__(self):
        self._client = None
        self._client_cls = None  # type: ignore
        self._auth_method = (os.getenv("GA4_AUTH_METHOD") or "").strip().lower() or None
        self._oauth_override: Optional[dict[str, str]] = None
        self._sa_path_override: Optional[str] = None

    # -------------------- factory helpers --------------------
    @classmethod
    def from_oauth_refresh_token(cls, client_id: str, client_secret: str, refresh_token: str) -> "GA4Client":
        """
        Convenience factory to force OAuth mode with explicit credentials.
        Useful for tests and when you want to bypass env vars.
        """
        inst = cls()
        inst._auth_method = "oauth"
        inst._oauth_override = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }
        return inst

    @classmethod
    def from_service_account_file(cls, path: str) -> "GA4Client":
        """
        Convenience factory to force Service Account mode with a specific key file.
        """
        inst = cls()
        inst._auth_method = "service_account"
        inst._sa_path_override = path
        return inst

    def fetch_daily_metrics(self, property_id: Optional[str] = None, days: int = 7) -> Dict[str, Any]:
        """
        Wrapper that returns a compact dict of daily metrics for the last `days` period.
        Keys match what our ingestion expects: organic_sessions, conversions, revenue,
        period_start, period_end, source_row_count.
        """
        days = max(1, int(days))
        end_dt = dt.date.today()
        start_dt = end_dt - dt.timedelta(days=days - 1)
        return self.fetch_summary(property_id=property_id, start_date=start_dt, end_date=end_dt)

    # -------------------- internal helpers --------------------
    def _load_client_class(self):
        if self._client_cls is None:
            try:
                from google.analytics.data_v1beta import BetaAnalyticsDataClient  # type: ignore
            except Exception as e:  # pragma: no cover - import guard
                raise GA4ConfigError(
                    "google-analytics-data library is not installed. "
                    "Install with: pip install google-analytics-data"
                ) from e
            self._client_cls = BetaAnalyticsDataClient
        return self._client_cls

    def _oauth_credentials(self):
        """Build Credentials from OAuth refresh token env vars."""
        if self._oauth_override:
            client_id = self._oauth_override["client_id"]
            client_secret = self._oauth_override["client_secret"]
            refresh_token = self._oauth_override["refresh_token"]
        else:
            client_id = os.getenv("GA4_CLIENT_ID")
            client_secret = os.getenv("GA4_CLIENT_SECRET")
            refresh_token = os.getenv("GA4_REFRESH_TOKEN")
        if not all([client_id, client_secret, refresh_token]):
            missing = [n for n, v in {
                "GA4_CLIENT_ID": client_id,
                "GA4_CLIENT_SECRET": client_secret,
                "GA4_REFRESH_TOKEN": refresh_token,
            }.items() if not v]
            raise GA4ConfigError(
                f"Missing OAuth env vars: {', '.join(missing)}. "
                "Set these in your .env or use service account auth."
            )
        try:
            from google.oauth2.credentials import Credentials  # type: ignore
        except Exception as e:  # pragma: no cover
            raise GA4ConfigError(
                "google-auth is required for OAuth. Install with: pip install google-auth"
            ) from e
        # token is None; the client will refresh using the refresh_token
        return Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/analytics.readonly"],
        )

    def _service_account_credentials(self):
        path = self._sa_path_override or os.getenv("GA4_CREDENTIALS_JSON") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not path or not os.path.exists(path):
            raise GA4ConfigError(
                "GA4 service account file not found. Set GA4_CREDENTIALS_JSON (or GOOGLE_APPLICATION_CREDENTIALS) to a valid path."
            )
        try:
            from google.oauth2 import service_account  # type: ignore
        except Exception as e:  # pragma: no cover
            raise GA4ConfigError(
                "google-auth is required for service accounts. Install with: pip install google-auth"
            ) from e
        return service_account.Credentials.from_service_account_file(
            path,
            scopes=["https://www.googleapis.com/auth/analytics.readonly"],
        )

    def _get_client(self):
        if self._client is not None:
            return self._client
        client_cls = self._load_client_class()

        # Choose auth method: explicit GA4_AUTH_METHOD, else infer
        method = self._auth_method
        if method not in {"oauth", "service_account", None}:
            raise GA4ConfigError("GA4_AUTH_METHOD must be 'oauth' or 'service_account' if set.")
        if method is None:
            # infer from env
            method = "oauth" if os.getenv("GA4_REFRESH_TOKEN") else "service_account"

        if method == "oauth":
            creds = self._oauth_credentials()
            self._client = client_cls(credentials=creds)
        else:
            # service account
            creds = self._service_account_credentials()
            self._client = client_cls(credentials=creds)

        return self._client

    def _resolve_property_id(self, property_id: Optional[str]) -> str:
        if property_id:
            return property_id
        # First, simple env var
        env_prop = os.getenv("GA4_PROPERTY_ID")
        if env_prop:
            return env_prop
        # Next, if exactly one GA4_PROPERTY_ID_* is set, use that
        candidates: list[str] = []
        for k, v in os.environ.items():
            if k.startswith("GA4_PROPERTY_ID_") and v:
                candidates.append(v)
        unique_vals = list({v for v in candidates})
        if len(unique_vals) == 1:
            return unique_vals[0]
        # Could not decide
        raise GA4ConfigError(
            "GA4 property id is required. Set GA4_PROPERTY_ID, pass property_id to fetch_summary(), "
            "or ensure only one GA4_PROPERTY_ID_* env var is defined."
        )

    @staticmethod
    def _to_date(d: dt.datetime | dt.date | str) -> str:
        if isinstance(d, (dt.datetime, dt.date)):
            return d.strftime("%Y-%m-%d")
        return str(d)

    # -------------------- public API --------------------
    def fetch_summary(
        self,
        property_id: Optional[str] = None,
        start_date: str | dt.date | dt.datetime = "7daysAgo",
        end_date: str | dt.date | dt.datetime = "today",
    ) -> Dict[str, Any]:
        """
        Run a simple GA4 report and return values mapped to AnalyticsSnapshot fields.

        Returns a dict with keys:
            organic_sessions (int), conversions (int), revenue (float),
            period_start (iso8601), period_end (iso8601), source_row_count (int)
        """
        prop = self._resolve_property_id(property_id)
        s = self._to_date(start_date)
        e = self._to_date(end_date)

        try:
            from google.analytics.data_v1beta.types import (  # type: ignore
                RunReportRequest,
                DateRange,
                Metric,
                Dimension,
            )
        except Exception as e:  # pragma: no cover - import guard
            raise GA4ConfigError(
                "google-analytics-data library is not installed. "
                "Install with: pip install google-analytics-data"
            ) from e

        request = RunReportRequest(
            property=f"properties/{prop}",
            dimensions=[Dimension(name="sessionDefaultChannelGroup")],
            metrics=[
                Metric(name="sessions"),
                Metric(name="conversions"),
                Metric(name="totalRevenue"),
            ],
            date_ranges=[DateRange(start_date=s, end_date=e)],
            limit=100000,
        )

        response = self._get_client().run_report(request)

        total_sessions = 0
        total_conversions = 0
        total_revenue = 0.0
        row_count = 0

        for row in getattr(response, "rows", []) or []:
            row_count += 1
            # dimension_values[0] is the channel group name, but we aggregate over all
            sessions = int(row.metric_values[0].value or 0)
            conversions = int(row.metric_values[1].value or 0)
            revenue = float(row.metric_values[2].value or 0.0)
            total_sessions += sessions
            total_conversions += conversions
            total_revenue += revenue

        def to_iso(dstr: str) -> str:
            # Normalize to UTC ISO strings for period_* fields
            try:
                if re.match(r"^\d{4}-\d{2}-\d{2}$", dstr):
                    return dt.datetime.fromisoformat(dstr + "T00:00:00").replace(tzinfo=dt.timezone.utc).isoformat().replace("+00:00", "Z")
                # allow direct ISO
                return dt.datetime.fromisoformat(dstr).astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
            except Exception:
                # handle relative tokens like 'today', 'yesterday', '7daysAgo'
                now = dt.datetime.utcnow().replace(microsecond=0)
                if dstr == "today":
                    start_dt = now
                elif dstr == "yesterday":
                    start_dt = now - dt.timedelta(days=1)
                else:
                    # e.g., '7daysAgo'
                    m = re.match(r"(\d+)daysAgo", dstr)
                    days = int(m.group(1)) if m else 7
                    start_dt = now - dt.timedelta(days=days)
                return start_dt.replace(tzinfo=dt.timezone.utc).isoformat().replace("+00:00", "Z")

        return {
            "organic_sessions": int(total_sessions),
            "conversions": int(total_conversions),
            "revenue": round(float(total_revenue), 2),
            "period_start": to_iso(s),
            "period_end": to_iso(e),
            "source_row_count": row_count,
        }


def load_ga4_client() -> GA4Client:
    """Helper to construct a GA4Client and surface friendly errors."""
    return GA4Client()