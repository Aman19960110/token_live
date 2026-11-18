
"""
Watchlist Studio - web front-end for watchlist_generator.py
  pip install streamlit pandas nselib yfinance tqdm
  streamlit run watchlist_app.py        (keep watchlist_generator.py in the same folder)

MASTER LIST = every stock. ADDSTRIKES is fetched for ALL of them (your process_stock logic).
Each stock is assigned to exactly ONE sheet (or none), so no stock repeats across watchlists.
"""
import copy, hashlib, hmac, io, json, os, re, secrets, time, zipfile
from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st
import module.watchlist_generator as wg

st.set_page_config(page_title="Watchlist Studio", layout="wide")
LINE = re.compile(r"^STOCK_BASESCRIPT:([^|]+)\|CE:(\d+)\|PE:(\d+)\|ADDSTRIKES:([^|]*)\|REMAP%:(\d+\.\d{2})$")
NONE = "—"
SS = st.session_state
PROFILE_DIR = Path(os.environ.get("WATCHLIST_PROFILE_DIR", "user_profiles"))   # one JSON file per user
USER_RE = re.compile(r"^[a-z0-9_\-]{2,32}$")
SYM_RE = re.compile(r"^[A-Z0-9&\-]+$")
for _k, _v in dict(oi=wg.OI_THRESHOLD, atm=wg.ATM_PCT, workers=wg.MAX_WORKERS, retries=wg.RETRIES,
                   onfail=wg.ON_FAIL, remap=wg.REMAP).items():
    SS.setdefault(_k, _v)


def blank(i):
    return {"name": f"Watchlist{i}", "ce": 5, "pe": 5, "strike_format": "auto", "trailing_newline": False}


def sync_expiry_sheet_widgets(expiry):
    prefixes = {"name": "nm", "ce": "ce", "pe": "pe", "strike_format": "sf", "trailing_newline": "tn"}
    for i, sheet in enumerate(SS.expiry_sheets[expiry]):
        for field in ("name", "ce", "pe", "strike_format", "trailing_newline"):
            SS[f"{prefixes[field]}_{expiry}_{i}"] = sheet[field]


def from_sheets(sheets):
    """sheets (with 'stocks') -> master list + assignment; first sheet wins on duplicates."""
    sheets = wg.dedupe_sheets(copy.deepcopy(sheets), announce=False)
    SS.master = wg.master_list(sheets)
    SS.assign = {s: sh["name"] for sh in sheets for s in sh["stocks"]}
    SS.cfg = [{k: v for k, v in sh.items() if k != "stocks"} for sh in sheets]
    for expiry in SS.get("expiry_sheets", {}):
        SS.expiry_sheets[expiry] = copy.deepcopy(SS.cfg)
        SS.expiry_assign[expiry] = SS.assign.copy()
        SS[f"expiry_n_{expiry}"] = len(SS.cfg)
        sync_expiry_sheet_widgets(expiry)
    SS.texts = None; SS.ver = SS.get("ver", 0) + 1


def reset():
    from_sheets(wg.DEFAULT_SHEETS)


if "cfg" not in SS:
    SS.update(strikes={}, strikes_expiry=None, failed=[], fetched_at=None, notes=[])
    reset()
SS.setdefault("strikes_by_expiry", {})
SS.setdefault("failed_by_expiry", {})
SS.setdefault("fetched_at_by_expiry", {})
SS.setdefault("expiry_settings", {})
SS.setdefault("expiry_sheets", {})
SS.setdefault("expiry_assign", {})
if not SS.strikes_by_expiry and SS.get("strikes_expiry") and SS.get("strikes"):
    legacy_expiry = SS.strikes_expiry
    SS.strikes_by_expiry[legacy_expiry] = SS.strikes
    SS.failed_by_expiry[legacy_expiry] = SS.get("failed", [])
    if SS.get("fetched_at"):
        SS.fetched_at_by_expiry[legacy_expiry] = SS.fetched_at


def resize_expiry(expiry):
    cfg = SS.expiry_sheets[expiry]
    n = SS[f"expiry_n_{expiry}"]
    while len(cfg) < n:
        cfg.append(blank(len(cfg) + 1))
    del cfg[n:]
    names = {c["name"] for c in cfg}
    assign = SS.expiry_assign[expiry]
    SS.expiry_assign[expiry] = {s: (v if v in names else "") for s, v in assign.items()}
    sync_expiry_sheet_widgets(expiry)
    SS.texts = None; SS.ver += 1


def move_sheet_to_expiry(source, index, expiry_widget):
    target = SS[expiry_widget]
    if source == target:
        return

    source_cfg = SS.expiry_sheets[source]
    sheet = source_cfg[index]
    name = sheet["name"]
    target_cfg = SS.expiry_sheets[target]
    matching = next((i for i, existing in enumerate(target_cfg) if existing["name"] == name), None)
    if matching is not None and target_cfg[matching] != sheet:
        SS[expiry_widget] = source
        SS.notes = [f"Cannot move {name} to {target}: a watchlist with that name has different settings. "
                    "Rename one of the watchlists first."]
        return

    source_assign = SS.expiry_assign[source]
    target_assign = SS.expiry_assign[target]
    symbols = [symbol for symbol, owner in source_assign.items() if owner == name]
    if matching is None:
        target_cfg.append(copy.deepcopy(sheet))
    for symbol in symbols:
        source_assign[symbol] = ""
        target_assign[symbol] = name

    source_cfg.pop(index)
    if not source_cfg:
        source_cfg.append(blank(1))
    SS[f"expiry_n_{source}"] = len(source_cfg)
    SS[f"expiry_n_{target}"] = len(target_cfg)
    sync_expiry_sheet_widgets(source)
    sync_expiry_sheet_widgets(target)
    SS.pop(f"up_{source}_{index}", None)
    SS.pop(expiry_widget, None)
    SS.notes = [f"Moved {name} and {len(symbols)} assigned stock(s) from {source} to {target}."]
    SS.texts = None; SS.ver += 1


def load_file_into_sheet(expiry, index):
    key = f"up_{expiry}_{index}"
    uploaded = SS.get(key)
    if uploaded is None:
        SS.notes = ["Choose a .txt watchlist beside the sheet settings first."]
        return

    text = uploaded.getvalue().decode("utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    rows = [LINE.match(line) for line in lines]
    if not rows or any(row is None for row in rows):
        SS.notes = [f"{uploaded.name} has no watchlist lines or contains an invalid line; nothing was loaded."]
        return

    cfg = SS.expiry_sheets[expiry]
    sheet = cfg[index]
    name = sheet["name"]
    symbols = list(dict.fromkeys(row.group(1) for row in rows))
    for symbol in symbols:
        if symbol not in SS.master:
            SS.master.append(symbol)
            SS.assign[symbol] = ""
            for assignments in SS.expiry_assign.values():
                assignments[symbol] = ""

    assignments = SS.expiry_assign[expiry]
    for symbol, owner in list(assignments.items()):
        if owner == name:
            assignments[symbol] = ""
    for symbol in symbols:
        assignments[symbol] = name

    sheet.update({
        "ce": int(rows[0].group(2)),
        "pe": int(rows[0].group(3)),
        "strike_format": "decimal2" if any("." in row.group(4) for row in rows) else "auto",
        "trailing_newline": text.endswith("\n"),
    })
    sync_expiry_sheet_widgets(expiry)
    SS.notes = [f"Loaded {len(symbols)} stock(s) from {uploaded.name} into {name} for {expiry}."]
    SS.texts = None; SS.ver += 1


def add_master():
    for sym in re.split(r"[,\s]+", SS.newsyms.upper()):
        if sym and re.match(r"^[A-Z0-9&\-]+$", sym) and sym not in SS.master:
            SS.master.append(sym)
            for assign in SS.expiry_assign.values():
                assign[sym] = ""
    SS.newsyms = ""; SS.texts = None; SS.ver += 1


def load_fno():
    try:
        from nselib import capital_market
        for sym in capital_market.fno_equity_list()["symbol"]:
            sym = str(sym).strip().upper()
            if sym not in SS.master:
                SS.master.append(sym)
                for assign in SS.expiry_assign.values():
                    assign[sym] = ""
        SS.notes = ["NSE F&O list merged into the master list (new stocks are unassigned)."]
    except Exception as e:
        SS.notes = [f"Could not load the NSE F&O list: {e}"]
    SS.texts = None; SS.ver += 1


def bulk(expiry, view, target):
    assign = SS.expiry_assign[expiry]
    for s in view:
        assign[s] = "" if target == NONE else target
    SS.texts = None; SS.ver += 1


def distribute(expiry):
    names = [c["name"] for c in SS.expiry_sheets[expiry]]
    assign = SS.expiry_assign[expiry]
    free = [s for s in SS.master if not assign.get(s)]
    for k, s in enumerate(free):
        assign[s] = names[k % len(names)]
    SS.texts = None; SS.ver += 1


def delete_unassigned():
    SS.master = [s for s in SS.master if any(a.get(s) for a in SS.expiry_assign.values())]
    for expiry, assign in SS.expiry_assign.items():
        SS.expiry_assign[expiry] = {s: assign.get(s, "") for s in SS.master}
    SS.assign = {s: SS.assign.get(s, "") for s in SS.master}
    SS.texts = None; SS.ver += 1


def apply_list_to_expiries(cfg, master, assign):
    SS.cfg, SS.master, SS.assign = cfg, master, assign
    for expiry in SS.get("expiry_sheets", {}):
        SS.expiry_sheets[expiry] = copy.deepcopy(cfg)
        SS.expiry_assign[expiry] = assign.copy()
        SS[f"expiry_n_{expiry}"] = len(cfg)
        sync_expiry_sheet_widgets(expiry)


def apply_expiry_lists(expiry_lists):
    for expiry, data in expiry_lists.items():
        SS.expiry_sheets[expiry] = data["cfg"]
        SS.expiry_assign[expiry] = data["assign"]
        SS[f"expiry_n_{expiry}"] = len(data["cfg"])
        sync_expiry_sheet_widgets(expiry)


# ------------------------------ per-user saved default list ------------------------------
def uid(name):
    return re.sub(r"[^a-z0-9_\-]", "", (name or "").strip().lower())


def pfile(u):
    return PROFILE_DIR / f"{u}.json"


def hash_pin(pin, salt):
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 120_000).hex()


def pin_ok(prof, pin):
    rec = prof.get("pin")
    return True if not rec else hmac.compare_digest(hash_pin(pin or "", rec["salt"]), rec["hash"])


def clean_profile(prof):
    """Validate a profile file (it may have been edited by hand)."""
    def clean_cfg(raw):
        cfg = []
        for c in raw:
            name = str(c["name"]).strip()
            if not re.match(r"^[\w\- ]+$", name) or c["strike_format"] not in wg.MODES:
                raise ValueError("bad sheet settings")
            cfg.append({"name": name, "ce": int(c["ce"]), "pe": int(c["pe"]),
                        "strike_format": c["strike_format"], "trailing_newline": bool(c["trailing_newline"])})
        if not cfg or len(cfg) > 20 or len({c["name"] for c in cfg}) != len(cfg):
            raise ValueError("bad sheet list")
        return cfg

    cfg = clean_cfg(prof["cfg"])
    master = list(dict.fromkeys(str(s) for s in prof["master"]))
    if not all(SYM_RE.match(s) for s in master):
        raise ValueError("bad symbol in master list")
    names = {c["name"] for c in cfg}
    assign = {s: (prof["assign"].get(s) if prof["assign"].get(s) in names else "") for s in master}
    expiry_lists = {}
    for expiry, data in prof.get("expiry_lists", {}).items():
        datetime.strptime(expiry, "%d-%m-%Y")
        expiry_cfg = clean_cfg(data["cfg"])
        expiry_names = {c["name"] for c in expiry_cfg}
        expiry_assign = data.get("assign", {})
        expiry_lists[expiry] = {
            "cfg": expiry_cfg,
            "assign": {s: (expiry_assign.get(s) if expiry_assign.get(s) in expiry_names else "")
                       for s in master},
        }
    pr = prof.get("prefs", {})
    prefs = {"oi": max(0, int(pr.get("oi", wg.OI_THRESHOLD))),
             "atm": min(1.0, max(0.0, float(pr.get("atm", wg.ATM_PCT)))),
             "retries": min(5, max(0, int(pr.get("retries", wg.RETRIES)))),
             "onfail": pr.get("onfail") if pr.get("onfail") in ("empty", "skip") else "empty",
             "remap": pr.get("remap") if re.match(r"^\d+\.\d{2}$", str(pr.get("remap", ""))) else wg.REMAP}
    return cfg, master, assign, prefs, expiry_lists


def snapshot():
    """Everything a user needs to restore their default list (no PIN, no fetched strikes)."""
    return {"version": 1, "cfg": SS.cfg, "master": SS.master, "assign": SS.assign,
            "expiry_lists": {
                expiry: {"cfg": cfg, "assign": SS.expiry_assign.get(expiry, {})}
                for expiry, cfg in SS.expiry_sheets.items()
            },
            "prefs": {k: SS[k] for k in ("oi", "atm", "retries", "onfail", "remap")}}


def do_import():
    f = SS.get("impfile")
    if f is None:
        SS.umsg = ("info", "Choose a saved list file first."); return
    try:
        if f.size > 2_000_000:
            raise ValueError("file is too large")
        cfg, master, assign, prefs, expiry_lists = clean_profile(json.loads(f.getvalue().decode("utf-8")))
    except Exception as e:
        SS.umsg = ("error", f"Not a valid saved-list file: {e}"); return
    apply_list_to_expiries(cfg, master, assign)
    apply_expiry_lists(expiry_lists)
    SS.update(prefs); SS.texts = None; SS.ver += 1
    SS.umsg = ("success", f"Restored {len(master)} stocks from the file."
                          + (" Click “Save as my default” to keep it on the server too." if SS.get("user") else ""))


def do_login():
    u = uid(SS.uname)
    if not USER_RE.match(u):
        SS.umsg = ("error", "Name must be 2–32 letters, digits, _ or -."); return
    if not pfile(u).exists():
        SS.user = u
        SS.umsg = ("info", f"New profile “{u}”. Arrange your stocks, then click “Save as my default”."); return
    try:
        prof = json.loads(pfile(u).read_text("utf-8"))
        if not pin_ok(prof, SS.upin):
            time.sleep(1); SS.umsg = ("error", "Wrong PIN."); return
        cfg, master, assign, prefs, expiry_lists = clean_profile(prof)
    except Exception as e:
        SS.umsg = ("error", f"Could not read profile: {e}"); return
    SS.user = u
    apply_list_to_expiries(cfg, master, assign)
    apply_expiry_lists(expiry_lists)
    SS.update(prefs); SS.texts = None; SS.ver += 1
    SS.umsg = ("success", f"Loaded {u}’s default list ({len(master)} stocks).")


def do_save():
    u = SS.get("user")
    if not u:
        SS.umsg = ("error", "Enter your name and click “Log in / load” first."); return
    old = None
    try:
        if pfile(u).exists():
            old = json.loads(pfile(u).read_text("utf-8"))
            if not pin_ok(old, SS.upin):
                time.sleep(1); SS.umsg = ("error", "Wrong PIN, nothing saved."); return
        pin = (old or {}).get("pin")
        if not pin and SS.upin:
            if len(SS.upin) < 4:
                SS.umsg = ("error", "PIN must be at least 4 characters."); return
            salt = secrets.token_hex(16); pin = {"salt": salt, "hash": hash_pin(SS.upin, salt)}
        data = {**snapshot(), "pin": pin, "saved_at": datetime.now().isoformat(timespec="seconds")}
        clean_profile(data)                                   # never save something we could not load again
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = pfile(u).with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), "utf-8"); os.replace(tmp, pfile(u))
        SS.umsg = ("success", f"Saved as {u}’s default list." + ("" if pin else " (no PIN set: anyone with your name can overwrite it)"))
    except Exception as e:
        SS.umsg = ("error", f"Could not save: {e}")


def do_delete():
    u = SS.get("user")
    try:
        if u and pfile(u).exists():
            if not pin_ok(json.loads(pfile(u).read_text("utf-8")), SS.upin):
                time.sleep(1); SS.umsg = ("error", "Wrong PIN, nothing deleted."); return
            pfile(u).unlink()
            SS.umsg = ("success", f"Deleted saved list for {u}.")
        else:
            SS.umsg = ("info", "No saved list to delete.")
    except Exception as e:
        SS.umsg = ("error", f"Could not delete: {e}")


def do_logout():
    SS.user = None; SS.umsg = ("info", "Logged out. The lists on screen are unchanged.")


# ------------------------------ sidebar ------------------------------
with st.sidebar:
    st.header("My profile")
    st.text_input("Your name", value=st.query_params.get("user", ""), key="uname")
    st.text_input("PIN (optional, 4+ characters)", type="password", key="upin")
    pc = st.columns(2)
    pc[0].button("Log in / load", on_click=do_login)
    pc[1].button("Save as my default", on_click=do_save)
    if SS.get("user"):
        st.caption(f"Logged in as **{SS.user}**")
        with st.expander("More"):
            st.button("Log out", on_click=do_logout)
            st.button("Delete my saved list", on_click=do_delete)
    if SS.get("umsg"):
        getattr(st, SS.umsg[0])(SS.umsg[1])
    with st.expander("Backup: download / restore my list"):
        st.download_button("Download my list", json.dumps(snapshot(), indent=1),
                           f"{SS.get('user') or 'my'}_watchlist_default.json", "application/json")
        st.file_uploader("Restore from a saved list file", type="json", key="impfile")
        st.button("Restore this file", on_click=do_import)
    st.divider()
    st.header("Settings")
    expiry_text = st.text_area("Expiries (dd-mm-yyyy, comma or newline separated)", wg.EXPIRY_DATE)
    expiries = list(dict.fromkeys(re.split(r"[,\s]+", expiry_text.strip()))) if expiry_text.strip() else []
    if not expiries:
        st.error("Enter at least one expiry date.")
        st.stop()
    for expiry in expiries:
        try:
            datetime.strptime(expiry, "%d-%m-%Y")
        except ValueError:
            st.error(f"Expiry {expiry!r} must look like 29-12-2026")
            st.stop()
        if expiry not in SS.expiry_sheets:
            SS.expiry_sheets[expiry] = copy.deepcopy(SS.cfg)
            SS.expiry_assign[expiry] = SS.assign.copy()
        SS.setdefault(f"expiry_n_{expiry}", len(SS.expiry_sheets[expiry]))
        defaults = {"oi": SS.oi, "atm": SS.atm, "workers": SS.workers, "retries": SS.retries,
                    "onfail": SS.onfail, "remap": SS.remap}
        settings = SS.expiry_settings.setdefault(expiry, defaults.copy())
        for field in ("oi", "atm", "workers", "retries", "onfail", "remap"):
            SS.setdefault(f"expiry_{field}_{expiry}", settings.get(field, defaults[field]))
        with st.expander(f"Settings for {expiry}", expanded=len(expiries) == 1):
            st.number_input("OI threshold", min_value=0, key=f"expiry_oi_{expiry}")
            st.number_input("ATM % (0.00 = as script)", 0.0, 1.0, step=0.01, format="%.2f",
                            key=f"expiry_atm_{expiry}")
            st.number_input("Max workers", 1, 32, key=f"expiry_workers_{expiry}")
            st.number_input("Retries for failed stocks", 0, 5, key=f"expiry_retries_{expiry}")
            st.selectbox("If a stock has no data", ["empty", "skip"], key=f"expiry_onfail_{expiry}",
                         help="empty = keep line with blank ADDSTRIKES; skip = drop the stock")
            st.text_input("REMAP% value", key=f"expiry_remap_{expiry}")
            st.number_input("Number of sheets", 1, 20, key=f"expiry_n_{expiry}",
                            on_change=resize_expiry, args=(expiry,))
        settings.update({
            "oi": SS[f"expiry_oi_{expiry}"],
            "atm": SS[f"expiry_atm_{expiry}"],
            "workers": SS[f"expiry_workers_{expiry}"],
            "retries": SS[f"expiry_retries_{expiry}"],
            "onfail": SS[f"expiry_onfail_{expiry}"],
            "remap": SS[f"expiry_remap_{expiry}"],
        })
        if not re.match(r"^\d+\.\d{2}$", settings["remap"]):
            st.error(f"REMAP% for {expiry} must look like 1.00")
            st.stop()
    st.button("Reset to default lists", on_click=reset)
st.title("Watchlist Studio")
for n in SS.notes:
    st.info(n)

# ------------------------------ master list ------------------------------
st.subheader(f"1. Master list ({len(SS.master)} stocks)")
a = st.columns([3, 1, 1])
a[0].text_input("Add stocks (comma or space separated)", key="newsyms", on_change=add_master)
a[1].button("Load NSE F&O list", on_click=load_fno)
flt = a[2].text_input("Filter").strip().upper()
view = [s for s in SS.master if flt in s]
st.button("Delete stocks unassigned for every expiry", on_click=delete_unassigned)

st.subheader("2. Sheets and stock assignments by expiry")
for expiry, tab in zip(expiries, st.tabs(expiries)):
    with tab:
        cfg = SS.expiry_sheets[expiry]
        assign = SS.expiry_assign[expiry]
        for i, sheet in enumerate(cfg):
            c = st.columns([1.5, 0.55, 0.55, 1.1, 1.1, 1.1, 2, 0.7])
            old = sheet["name"]
            sheet["name"] = c[0].text_input("File name", old, key=f"nm_{expiry}_{i}").strip()
            if sheet["name"] != old:
                assign = {s: (sheet["name"] if v == old else v) for s, v in assign.items()}
                SS.expiry_assign[expiry] = assign
                SS.ver += 1
            sheet["ce"] = int(c[1].number_input("CE", 0, 999, sheet["ce"], key=f"ce_{expiry}_{i}"))
            sheet["pe"] = int(c[2].number_input("PE", 0, 999, sheet["pe"], key=f"pe_{expiry}_{i}"))
            sheet["strike_format"] = c[3].selectbox(
                "Strike format", list(wg.MODES), list(wg.MODES).index(sheet["strike_format"]),
                key=f"sf_{expiry}_{i}",
                help="auto: whole strikes as 2200, a stock with any decimal strike fully as 157.50")
            sheet["trailing_newline"] = c[4].checkbox(
                "Trailing newline", sheet["trailing_newline"], key=f"tn_{expiry}_{i}")
            expiry_widget = f"sheet_exp_{expiry}_{i}"
            c[5].selectbox("Expiry", expiries, index=expiries.index(expiry), key=expiry_widget,
                           on_change=move_sheet_to_expiry,
                           args=(expiry, i, expiry_widget))
            c[6].file_uploader("Upload watchlist", type="txt", key=f"up_{expiry}_{i}")
            c[7].button("Load", on_click=load_file_into_sheet, args=(expiry, i),
                        key=f"load_{expiry}_{i}")
        names = [sheet["name"] for sheet in cfg]
        b = st.columns([2, 1, 1.2, 3])
        tgt = b[0].selectbox("Assign shown stocks to", names + [NONE], key=f"tgt_{expiry}")
        b[1].button("Apply", on_click=bulk, args=(expiry, view, tgt), key=f"apply_{expiry}")
        b[2].button("Spread unassigned evenly", on_click=distribute, args=(expiry,), key=f"spread_{expiry}")
        cnt = {n: sum(1 for s in SS.master if assign.get(s) == n) for n in names}
        b[3].markdown(" · ".join(f"**{n}** {v}" for n, v in cnt.items())
                      + f" · **unassigned** {len(SS.master) - sum(cnt.values())}")

        strikes = SS.strikes_by_expiry.get(expiry, {})
        df = pd.DataFrame({"Symbol": view, "Sheet": [assign.get(s) or NONE for s in view],
                           "Strikes": [len(strikes[s]) if s in strikes else None for s in view],
                           "Range": [f"{strikes[s][0]:g}–{strikes[s][-1]:g}" if strikes.get(s) else ""
                                     for s in view]})
        ed = st.data_editor(
            df, hide_index=True, height=420, disabled=["Symbol", "Strikes", "Range"],
            key=f"ed{SS.ver}_{expiry}_{flt}",
            column_config={"Sheet": st.column_config.SelectboxColumn(
                "Sheet", options=names + [NONE], required=True),
                "Strikes": st.column_config.NumberColumn(f"Strikes ({expiry})")})
        for symbol, sheet_name in zip(ed["Symbol"], ed["Sheet"]):
            assign[symbol] = "" if sheet_name == NONE else sheet_name

# ------------------------------ refresh + build ------------------------------
st.subheader("3. Refresh and build")
syms = list(SS.master)
c1, c2 = st.columns(2)
if c1.button(f"Refresh ADDSTRIKES for ALL {len(syms)} stocks × {len(expiries)} expiries",
             type="primary", disabled=not syms):
    with st.spinner("Fetching option chains (this can take several minutes)…"):
        for expiry in expiries:
            settings = SS.expiry_settings[expiry]
            res = wg.fetch_add_strikes(
                syms, expiry_date=expiry, oi_threshold=settings["oi"], atm_pct=settings["atm"],
                max_workers=settings["workers"], retries=settings["retries"])
            SS.strikes_by_expiry[expiry] = res
            SS.failed_by_expiry[expiry] = [s for s in syms if s not in res]
            SS.fetched_at_by_expiry[expiry] = datetime.now().strftime("%d-%b %H:%M:%S")
    SS.texts = None; SS.ver += 1; st.rerun()
for expiry in expiries:
    fetched_at = SS.fetched_at_by_expiry.get(expiry)
    if fetched_at:
        c1.caption(f"Last refresh for {expiry}: {fetched_at}")
        failed = SS.failed_by_expiry.get(expiry, [])
        if failed:
            st.warning(f"No data for {len(failed)} stock(s) for {expiry}: {', '.join(failed)} "
                       f"→ handled as “{SS.expiry_settings[expiry]['onfail']}”.")
        missing = [s for s in syms if s not in SS.strikes_by_expiry.get(expiry, {})]
        if missing:
            st.info(f"{len(missing)} master stock(s) for {expiry} not refreshed yet: refresh again before building.")
    else:
        c1.caption(f"No strike data fetched yet for {expiry}.")

if c2.button("Build files (validate format)"):
    try:
        texts = {}
        for expiry in expiries:
            cfg = SS.expiry_sheets[expiry]
            names = [sheet["name"] for sheet in cfg]
            if len(set(names)) != len(names) or not all(re.match(r"^[\w\- ]+$", n) for n in names):
                raise ValueError(f"{expiry}: sheet file names must be unique and use letters, digits, space, _ or - only.")
            assign = SS.expiry_assign[expiry]
            out = [{**sheet, "stocks": [s for s in SS.master if assign.get(s) == sheet["name"]]}
                   for sheet in cfg]
            settings = SS.expiry_settings[expiry]
            strikes = SS.strikes_by_expiry.get(expiry, {})
            built = wg.generate_watchlists(
                out, fetcher=lambda ss, strikes=strikes: {s: strikes[s] for s in ss if s in strikes},
                write=False, on_fail=settings["onfail"], remap=settings["remap"])
            texts.update({f"{name}_{expiry}": text for name, text in built.items()})
        SS.texts = texts
    except (ValueError, KeyError) as e:
        SS.texts = None; st.error(f"Format check failed, nothing built: {e}")

if SS.texts:
    st.success("All lines passed the format check. Within each expiry, no stock appears in more than one sheet.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, t in SS.texts.items():
            z.writestr(f"{n}.txt", t)
    st.download_button("Download all as ZIP", buf.getvalue(), "watchlists.zip", "application/zip")
    for tab, (n, t) in zip(st.tabs(list(SS.texts)), SS.texts.items()):
        with tab:
            st.caption(f"{len([l for l in t.splitlines() if l])} lines")
            st.download_button(f"Download {n}.txt", t, f"{n}.txt", "text/plain", key=f"dw_{n}")
            st.code(t, language=None)