"""Position reconciliation dashboard for RMSWEB reports.

This module combines the fetcher, reconciliation helpers, and the Streamlit UI
in a single file so it can be run directly as a page in the app.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests
import streamlit as st
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://nseweb.adroitfinancial.com:9090/RMSWEB"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded",
}


@dataclass
class Credentials:
    username: str = "VAIB"
    password: str = "123456"


@dataclass
class PositionFetcher:
    """Logs in to RMSWEB and fetches position reports by server code."""

    credentials: Credentials = field(default_factory=Credentials)
    base_url: str = BASE_URL
    session: requests.Session = field(default_factory=requests.Session)
    _logged_in: bool = False

    def login(self) -> None:
        """Authenticate and establish a session cookie."""
        login_url = f"{self.base_url}/loginprocess.action"
        payload = {
            "R1": "PWD",
            "username": self.credentials.username,
            "userpass": self.credentials.password,
            "submit": "Login",
        }
        resp = self.session.post(
            login_url, data=payload, headers=DEFAULT_HEADERS, verify=False
        )
        resp.raise_for_status()

        index_url = f"{self.base_url}/index.jsp?logintype=branch"
        index_resp = self.session.get(index_url, headers=DEFAULT_HEADERS, verify=False)
        index_resp.raise_for_status()
        self._logged_in = True

    def _ensure_logged_in(self) -> None:
        if not self._logged_in:
            self.login()

    def fetch_report(self, code: str) -> pd.DataFrame:
        """Fetch the data report for a given server code."""
        self._ensure_logged_in()
        url = f"{self.base_url}/datareport1"
        response = self.session.get(
            url, params={"code": code}, headers=DEFAULT_HEADERS, verify=False
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        target_table = soup.select_one("table#finsummary2")
        if target_table is not None:
            try:
                df_list = pd.read_html(io.StringIO(str(target_table)))
                if df_list:
                    return self._clean_dataframe(df_list[0])
            except Exception:
                pass

        for table in soup.find_all("table"):
            try:
                df_list = pd.read_html(io.StringIO(str(table)))
                if df_list:
                    return self._clean_dataframe(df_list[0])
            except Exception:
                continue

        raise ValueError(f"No parseable table found for code {code}")

    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize the parsed table into a reusable position DataFrame."""
        if df.empty:
            return df

        cleaned = df.copy()
        cleaned.columns = [str(c).strip() for c in cleaned.columns]

        if "Net Qty" in cleaned.columns:
            cleaned["Net Qty"] = pd.to_numeric(cleaned["Net Qty"], errors="coerce")
        if "STK" in cleaned.columns:
            cleaned["STK"] = pd.to_numeric(cleaned["STK"], errors="coerce")
        if "Type" in cleaned.columns:
            cleaned["Type"] = cleaned["Type"].astype(str).str.strip()

        return cleaned

        raise ValueError(f"No parseable table found for code {code}")


def fetch(code: str, credentials: Optional[Credentials] = None) -> pd.DataFrame:
    """Convenience helper to log in and fetch a report's first table."""
    fetcher = PositionFetcher(credentials=credentials or Credentials())
    return fetcher.fetch_report(code)


INDEX_LIST = ["NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY"]
INDEX_ALIASES = {
    "nifty": "NIFTY",
    "banknifty": "BANKNIFTY",
    "bknifty": "BANKNIFTY",
    "bank nifty": "BANKNIFTY",
    "bnf": "BANKNIFTY",
    "sensex": "SENSEX",
    "finnifty": "FINNIFTY",
    "fininfty": "FINNIFTY",
    "fin nifty": "FINNIFTY",
    "midcpnifty": "MIDCPNIFTY",
    "midcapnifty": "MIDCPNIFTY",
    "midcap nifty": "MIDCPNIFTY",
}

XX_ALIASES = {"xx", "ff", "fut", "future", "futures"}


def canonical_index(scrip: str) -> Optional[str]:
    """Map a scrip name to a canonical index name if it is an index."""
    if scrip is None:
        return None
    n = str(scrip).strip().lower().replace(" ", "")
    n_with_space = str(scrip).strip().lower()
    return INDEX_ALIASES.get(n) or INDEX_ALIASES.get(n_with_space) or None


def leg_type(cp: str) -> Optional[str]:
    """Map Call/Put/Type to CE/PE/XX."""
    if cp is None:
        return None
    n = str(cp).strip().lower()
    if n == "ce":
        return "CE"
    if n == "pe":
        return "PE"
    if n in XX_ALIASES:
        return "XX"
    return None


def round2(x: float) -> float:
    """Round to 2 decimal places."""
    return round(x * 100) / 100


@dataclass
class GroupResult:
    """Result for one Exchange|Scrip|Expiry group."""

    scrip: str
    expiry: str
    ce_qty: float
    pe_qty: float
    xx_qty: float
    qty_sum: float
    ce_stk_qty: float
    pe_stk_qty: float
    ce_cash: float
    pe_cash: float
    cash_sum: float
    cash_available: bool
    is_index: bool
    index_name: Optional[str]


@dataclass
class ServerResult:
    """Result for one server/client code."""

    server_name: str
    server_code: str
    groups: list[GroupResult]
    total_ce_qty: float
    total_pe_qty: float
    total_xx_qty: float
    total_qty_sum: float
    total_ce_cash: float
    total_pe_cash: float
    total_cash_sum: float
    matched: bool


def reconcile_dataframe(
    df: pd.DataFrame,
    atm_map: dict[str, float],
    has_cash_column: bool = False,
) -> list[GroupResult]:
    """Reconcile a position DataFrame into per-group summaries."""
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    required = ["EXCH", "Symbol", "Type", "Exp Date", "STK", "Net Qty"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Required column '{col}' not found in DataFrame. Columns: {list(df.columns)}")

    df = df.dropna(subset=["EXCH", "Type", "Net Qty"])
    df = df[df["EXCH"].astype(str).str.strip() != ""]

    df["LegType"] = df["Type"].apply(leg_type)
    df = df.dropna(subset=["LegType"])

    df["GroupKey"] = (
        df["EXCH"].astype(str).str.strip()
        + "||"
        + df["Symbol"].astype(str).str.strip()
        + "||"
        + df["Exp Date"].astype(str).str.strip()
    )

    results = []
    for key, group in df.groupby("GroupKey"):
        _, scrip, exp = key.split("||")

        ce = group[group["LegType"] == "CE"]
        pe = group[group["LegType"] == "PE"]
        xx = group[group["LegType"] == "XX"]

        ce_qty = pd.to_numeric(ce["Net Qty"], errors="coerce").sum()
        pe_qty = pd.to_numeric(pe["Net Qty"], errors="coerce").sum()
        xx_qty = pd.to_numeric(xx["Net Qty"], errors="coerce").sum()
        qty_sum = round2(ce_qty + pe_qty + xx_qty)

        ce_stk_qty = (
            pd.to_numeric(ce["STK"], errors="coerce")
            * pd.to_numeric(ce["Net Qty"], errors="coerce")
        ).sum()
        pe_stk_qty = (
            pd.to_numeric(pe["STK"], errors="coerce")
            * pd.to_numeric(pe["Net Qty"], errors="coerce")
        ).sum()

        idx_name = canonical_index(scrip)
        is_index = idx_name is not None
        cash_available = False
        ce_cash = 0.0
        pe_cash = 0.0

        if has_cash_column and "Cash" in group.columns:
            ce_cash = pd.to_numeric(ce["Cash"], errors="coerce").sum()
            pe_cash = pd.to_numeric(pe["Cash"], errors="coerce").sum()
            cash_available = True
        elif is_index:
            atm = atm_map.get(idx_name)
            if atm is not None and not np.isnan(atm):
                ce_cash = round2(atm * ce_qty - ce_stk_qty)
                pe_cash = round2(atm * pe_qty - pe_stk_qty)
                cash_available = True

        cash_sum = round2(ce_cash + pe_cash)

        results.append(
            GroupResult(
                scrip=scrip,
                expiry=exp,
                ce_qty=round2(ce_qty),
                pe_qty=round2(pe_qty),
                xx_qty=round2(xx_qty),
                qty_sum=qty_sum,
                ce_stk_qty=round2(ce_stk_qty),
                pe_stk_qty=round2(pe_stk_qty),
                ce_cash=round2(ce_cash),
                pe_cash=round2(pe_cash),
                cash_sum=cash_sum,
                cash_available=cash_available,
                is_index=is_index,
                index_name=idx_name,
            )
        )

    return results


def compute_server_summary(groups: list[GroupResult]) -> ServerResult:
    """Compute a server-level summary from group results."""
    total_ce_qty = round2(sum(g.ce_qty for g in groups))
    total_pe_qty = round2(sum(g.pe_qty for g in groups))
    total_xx_qty = round2(sum(g.xx_qty for g in groups))
    total_qty_sum = round2(total_ce_qty + total_pe_qty + total_xx_qty)

    total_ce_cash = round2(sum(g.ce_cash for g in groups if g.cash_available))
    total_pe_cash = round2(sum(g.pe_cash for g in groups if g.cash_available))
    total_cash_sum = round2(total_ce_cash + total_pe_cash)

    matched = round2(total_ce_qty + total_pe_qty) == 0

    return ServerResult(
        server_name="",
        server_code="",
        groups=groups,
        total_ce_qty=total_ce_qty,
        total_pe_qty=total_pe_qty,
        total_xx_qty=total_xx_qty,
        total_qty_sum=total_qty_sum,
        total_ce_cash=total_ce_cash,
        total_pe_cash=total_pe_cash,
        total_cash_sum=total_cash_sum,
        matched=matched,
    )


def fmt_num(n: float) -> str:
    """Format a number with thousands separators."""
    if n == 0:
        return "0"
    return f"{n:,.2f}"


def parse_client_codes(path: Optional[str | os.PathLike[str]] = None) -> dict[str, str]:
    """Read client codes from the local CLIENT_CODE.txt file."""
    if path is None:
        path = Path(__file__).with_name("CLIENT_CODE.txt")
    else:
        path = Path(path)
        if not path.is_absolute():
            path = Path(__file__).parent / path

    if not path.exists():
        raise FileNotFoundError(f"Client mapping file not found: {path}")

    mapping: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        client, code = line.split("=", 1)
        mapping[client.strip()] = code.strip()
    return mapping


st.set_page_config(page_title="Position Reconciliation", layout="wide")

st.title("📊 Position Reconciliation Dashboard")
st.info("Configure the ATM values in the sidebar and click Run Reconciliation to load the report.")

st.sidebar.header("ATM Values")
atm_map = {
    "NIFTY": st.sidebar.number_input("NIFTY", value=24500),
    "BANKNIFTY": st.sidebar.number_input("BANKNIFTY", value=52000),
    "SENSEX": st.sidebar.number_input("SENSEX", value=80000),
    "FINNIFTY": st.sidebar.number_input("FINNIFTY", value=24000),
    "MIDCPNIFTY": st.sidebar.number_input("MIDCPNIFTY", value=12000),
}

run = st.sidebar.button("Run Reconciliation")

if "dashboard_state" not in st.session_state:
    st.session_state.dashboard_state = None

if run:
    try:
        client_mapping = parse_client_codes()
    except FileNotFoundError as exc:
        st.warning(str(exc))
        st.stop()

    if not client_mapping:
        st.warning("No client mappings were loaded from CLIENT_CODE.txt.")
        st.stop()

    summaries = []
    detail_map = {}
    raw_map = {}

    progress = st.progress(0)
    total_clients = len(client_mapping)

    for i, (client, client_id) in enumerate(client_mapping.items()):
        try:
            df = fetch(client_id)
            raw_map[client] = df

            groups = reconcile_dataframe(df, atm_map)
            summary = compute_server_summary(groups)
            summary.server_name = client
            summary.server_code = client_id

            summaries.append(summary)
            detail_map[client] = groups
        except Exception as exc:
            st.warning(f"Skipping {client} ({client_id}): {exc}")

        progress.progress((i + 1) / max(total_clients, 1))

    if not summaries:
        st.error("No client reports were loaded successfully. Check the server credentials or report availability.")
        st.stop()

    summary_df = pd.DataFrame(
        [
            {
                "Client": s.server_name,
                "Status": "Matched" if s.matched else "Mismatch",
                "CE Qty": s.total_ce_qty,
                "PE Qty": s.total_pe_qty,
                "XX Qty": s.total_xx_qty,
                "Cash": s.total_cash_sum,
            }
            for s in summaries
        ]
    )

    st.session_state.dashboard_state = {
        "summary_df": summary_df,
        "detail_map": detail_map,
        "raw_map": raw_map,
    }
    st.session_state.selected_client = summary_df["Client"].iloc[0]

if st.session_state.dashboard_state is not None:
    dashboard_state = st.session_state.dashboard_state
    summary_df = dashboard_state["summary_df"]
    detail_map = dashboard_state["detail_map"]
    raw_map = dashboard_state["raw_map"]

    matched = summary_df["Status"].eq("Matched").sum()
    mismatch = len(summary_df) - matched

    c1, c2, c3 = st.columns(3)
    c1.metric("Servers", len(summary_df))
    c2.metric("Matched", matched)
    c3.metric("Mismatch", mismatch)

    st.divider()
    st.subheader("Server Summary")
    st.dataframe(summary_df, width="stretch")
    st.bar_chart(summary_df.set_index("Client")[["CE Qty", "PE Qty"]])

    st.divider()
    client = st.selectbox("Select Client", summary_df["Client"], key="selected_client")

    st.subheader("Group Details")
    groups = detail_map[client]
    detail_df = pd.DataFrame(
        [
            {
                "Scrip": g.scrip,
                "Expiry": g.expiry,
                "CE Qty": g.ce_qty,
                "PE Qty": g.pe_qty,
                "XX Qty": g.xx_qty,
                "Cash": g.cash_sum,
                "Status": "Matched" if round(g.ce_qty + g.pe_qty, 2) == 0 else "Mismatch",
            }
            for g in groups
        ]
    )
    st.dataframe(detail_df, width="stretch")

    st.subheader("Raw Positions")
    st.dataframe(raw_map[client], width="stretch")
