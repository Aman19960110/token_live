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
                    return self._clean_dataframe(df_list[1])
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
    data = fetcher.fetch_report(code)
    data.dropna(subset=['Symbol'],inplace=True)
    return data









class Position:
  def __init__(self,position_fetcher):
    self.position_fetcher = position_fetcher

  def get_cash_by_expiry(self,server_code):
    data = self.position_fetcher.fetch_report(server_code)
    cash = data.groupby('Exp Date').agg({'Net Value':'sum'}).reset_index().rename(columns={'Net Value':'Cash'})
    return cash

  def get_cash_by_stock_per_expiry(self,server_code):
    data = self.position_fetcher.fetch_report(server_code)
    mask = data.pivot_table('Net Value',index=['Exp Date','Symbol'],columns='Type',aggfunc='sum').reset_index()
    mask['cash_used'] =  mask['CE'] + mask['PE']
    return mask.sort_values('cash_used',ascending=False).reset_index()

  def check_postion(self,server_code):
    data = self.position_fetcher.fetch_report(server_code)
    if 'FF' in data['Type'].unique():
      mask = data.pivot_table('Net Qty',index=['Exp Date','Symbol'],columns='Type',aggfunc='sum').reset_index()
      mask = mask.fillna(0)
      pos = (abs(mask['CE'].sum()) == abs(mask['PE'].sum()) == abs(mask['FF'].sum()))
      if pos:
        return 'No MisMatch'
      else:
        return pos
    else:
      mask = data.pivot_table('Net Qty',index=['Exp Date','Symbol'],columns='Type',aggfunc='sum').reset_index()
      mask['mismatch'] = (abs(mask['CE']) == abs(mask['PE']))
      pos = mask[mask['mismatch']==False]
      if pos is None or pos.empty:
        return 'No MisMatch'
      else:
        return pos

  def get_exposuer(self,server_code):
    data = self.position_fetcher.fetch_report(server_code)
    exp = data[data['Type']=='FF']['Net Value'].sum()/10000000
    print(f'exposuer:{round(exp,2)}cr')

