
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


def from_sheets(sheets):
    """sheets (with 'stocks') -> master list + assignment; first sheet wins on duplicates."""
    sheets = wg.dedupe_sheets(copy.deepcopy(sheets), announce=False)
    SS.master = wg.master_list(sheets)
    SS.assign = {s: sh["name"] for sh in sheets for s in sh["stocks"]}
    SS.cfg = [{k: v for k, v in sh.items() if k != "stocks"} for sh in sheets]
    SS.n = len(SS.cfg); SS.texts = None; SS.ver = SS.get("ver", 0) + 1


def reset():
    from_sheets(wg.DEFAULT_SHEETS)


if "cfg" not in SS:
    SS.update(strikes={}, strikes_expiry=None, failed=[], fetched_at=None, notes=[])
    reset()


def resize():
    while len(SS.cfg) < SS.n:
        SS.cfg.append(blank(len(SS.cfg) + 1))
    del SS.cfg[SS.n:]
    names = {c["name"] for c in SS.cfg}
    SS.assign = {s: (v if v in names else "") for s, v in SS.assign.items()}
    SS.texts = None; SS.ver += 1


def load_files():
    new, notes = [], []
    for f in SS.get("up") or []:
        text = f.getvalue().decode("utf-8")
        rows = [m for m in (LINE.match(l) for l in text.splitlines() if l.strip()) if m]
        if rows:
            new.append({"name": Path(f.name).stem, "ce": int(rows[0].group(2)), "pe": int(rows[0].group(3)),
                        "strike_format": "decimal2" if any("." in m.group(4) for m in rows) else "auto",
                        "trailing_newline": text.endswith("\n"), "stocks": [m.group(1) for m in rows]})
    if new:
        before = sum(len(s["stocks"]) for s in new)
        from_sheets(new)
        SS.notes = [f"{before - len(SS.master)} repeated stock(s) removed (first sheet keeps it)."]


def add_master():
    for sym in re.split(r"[,\s]+", SS.newsyms.upper()):
        if sym and re.match(r"^[A-Z0-9&\-]+$", sym) and sym not in SS.master:
            SS.master.append(sym); SS.assign[sym] = ""
    SS.newsyms = ""; SS.texts = None; SS.ver += 1


def load_fno():
    try:
        from nselib import capital_market
        for sym in capital_market.fno_equity_list()["symbol"]:
            sym = str(sym).strip().upper()
            if sym not in SS.master:
                SS.master.append(sym); SS.assign[sym] = ""
        SS.notes = ["NSE F&O list merged into the master list (new stocks are unassigned)."]
    except Exception as e:
        SS.notes = [f"Could not load the NSE F&O list: {e}"]
    SS.texts = None; SS.ver += 1


def bulk(view, target):
    for s in view:
        SS.assign[s] = "" if target == NONE else target
    SS.texts = None; SS.ver += 1


def distribute():
    names = [c["name"] for c in SS.cfg]
    free = [s for s in SS.master if not SS.assign.get(s)]
    for k, s in enumerate(free):
        SS.assign[s] = names[k % len(names)]
    SS.texts = None; SS.ver += 1


def delete_unassigned():
    SS.master = [s for s in SS.master if SS.assign.get(s)]
    SS.assign = {s: SS.assign[s] for s in SS.master}; SS.ver += 1


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
    """Validate a profile file (it may have been edited by hand). Returns cfg, master, assign, prefs."""
    cfg = []
    for c in prof["cfg"]:
        name = str(c["name"]).strip()
        if not re.match(r"^[\w\- ]+$", name) or c["strike_format"] not in wg.MODES:
            raise ValueError("bad sheet settings")
        cfg.append({"name": name, "ce": int(c["ce"]), "pe": int(c["pe"]),
                    "strike_format": c["strike_format"], "trailing_newline": bool(c["trailing_newline"])})
    if not cfg or len(cfg) > 20 or len({c["name"] for c in cfg}) != len(cfg):
        raise ValueError("bad sheet list")
    master = list(dict.fromkeys(str(s) for s in prof["master"]))
    if not all(SYM_RE.match(s) for s in master):
        raise ValueError("bad symbol in master list")
    names = {c["name"] for c in cfg}
    assign = {s: (prof["assign"].get(s) if prof["assign"].get(s) in names else "") for s in master}
    pr = prof.get("prefs", {})
    prefs = {"oi": max(0, int(pr.get("oi", wg.OI_THRESHOLD))),
             "atm": min(1.0, max(0.0, float(pr.get("atm", wg.ATM_PCT)))),
             "retries": min(5, max(0, int(pr.get("retries", wg.RETRIES)))),
             "onfail": pr.get("onfail") if pr.get("onfail") in ("empty", "skip") else "empty",
             "remap": pr.get("remap") if re.match(r"^\d+\.\d{2}$", str(pr.get("remap", ""))) else wg.REMAP}
    return cfg, master, assign, prefs


def snapshot():
    """Everything a user needs to restore their default list (no PIN, no fetched strikes)."""
    return {"version": 1, "cfg": SS.cfg, "master": SS.master, "assign": SS.assign,
            "prefs": {k: SS[k] for k in ("oi", "atm", "retries", "onfail", "remap")}}


def do_import():
    f = SS.get("impfile")
    if f is None:
        SS.umsg = ("info", "Choose a saved list file first."); return
    try:
        if f.size > 2_000_000:
            raise ValueError("file is too large")
        cfg, master, assign, prefs = clean_profile(json.loads(f.getvalue().decode("utf-8")))
    except Exception as e:
        SS.umsg = ("error", f"Not a valid saved-list file: {e}"); return
    SS.cfg, SS.master, SS.assign, SS.n = cfg, master, assign, len(cfg)
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
        cfg, master, assign, prefs = clean_profile(prof)
    except Exception as e:
        SS.umsg = ("error", f"Could not read profile: {e}"); return
    SS.user, SS.cfg, SS.master, SS.assign, SS.n = u, cfg, master, assign, len(cfg)
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
    expiry = st.text_input("Expiry (dd-mm-yyyy)", wg.EXPIRY_DATE)
    st.number_input("OI threshold", 0, key="oi")
    st.number_input("ATM %  (0.00 = as script)", 0.0, 1.0, step=0.01, format="%.2f", key="atm")
    st.number_input("Max workers", 1, 32, key="workers")
    st.number_input("Retries for failed stocks", 0, 5, key="retries")
    st.selectbox("If a stock has no data", ["empty", "skip"], key="onfail",
                 help="empty = keep line with blank ADDSTRIKES; skip = drop the stock")
    st.text_input("REMAP% value", key="remap")
    st.number_input("Number of sheets", 1, 20, key="n", on_change=resize)
    st.file_uploader("Load master list from existing .txt files", accept_multiple_files=True, type="txt", key="up")
    st.button("Use uploaded files", on_click=load_files)
    st.button("Reset to default lists", on_click=reset)
try:
    datetime.strptime(expiry, "%d-%m-%Y")
except ValueError:
    st.error("Expiry must look like 29-12-2026"); st.stop()
if not re.match(r"^\d+\.\d{2}$", SS.remap):
    st.error("REMAP% must look like 1.00"); st.stop()

st.title("Watchlist Studio")
for n in SS.notes:
    st.info(n)

# ------------------------------ sheet settings ------------------------------
st.subheader("1. Sheets")
for i, cfg in enumerate(SS.cfg):
    c = st.columns([2, 1, 1, 1.4, 1.4])
    old = cfg["name"]
    cfg["name"] = c[0].text_input("File name", old, key=f"nm{i}").strip()
    if cfg["name"] != old:
        SS.assign = {s: (cfg["name"] if v == old else v) for s, v in SS.assign.items()}; SS.ver += 1
    cfg["ce"] = int(c[1].number_input("CE", 0, 999, cfg["ce"], key=f"ce{i}"))
    cfg["pe"] = int(c[2].number_input("PE", 0, 999, cfg["pe"], key=f"pe{i}"))
    cfg["strike_format"] = c[3].selectbox("Strike format", list(wg.MODES), list(wg.MODES).index(cfg["strike_format"]),
                                          key=f"sf{i}", help="auto: whole strikes as 2200, a stock with any decimal strike fully as 157.50")
    cfg["trailing_newline"] = c[4].checkbox("Trailing newline", cfg["trailing_newline"], key=f"tn{i}")
names = [c["name"] for c in SS.cfg]

# ------------------------------ master list ------------------------------
st.subheader(f"2. Master list ({len(SS.master)} stocks) — each stock goes to one sheet only")
a = st.columns([3, 1, 1])
a[0].text_input("Add stocks (comma or space separated)", key="newsyms", on_change=add_master)
a[1].button("Load NSE F&O list", on_click=load_fno)
flt = a[2].text_input("Filter").strip().upper()
view = [s for s in SS.master if flt in s]
b = st.columns([2, 1, 1.2, 1.2, 3])
tgt = b[0].selectbox("Assign shown stocks to", names + [NONE])
b[1].button("Apply", on_click=bulk, args=(view, tgt))
b[2].button("Spread unassigned evenly", on_click=distribute)
b[3].button("Delete unassigned", on_click=delete_unassigned)
cnt = {n: sum(1 for s in SS.master if SS.assign.get(s) == n) for n in names}
b[4].markdown(" · ".join(f"**{n}** {v}" for n, v in cnt.items()) + f" · **unassigned** {len(SS.master) - sum(cnt.values())}")

K = SS.strikes
df = pd.DataFrame({"Symbol": view, "Sheet": [SS.assign.get(s) or NONE for s in view],
                   "Strikes": [len(K[s]) if s in K else None for s in view],
                   "Range": [f"{K[s][0]:g}–{K[s][-1]:g}" if K.get(s) else "" for s in view]})
ed = st.data_editor(df, hide_index=True, height=420, disabled=["Symbol", "Strikes", "Range"], key=f"ed{SS.ver}_{flt}",
                    column_config={"Sheet": st.column_config.SelectboxColumn("Sheet", options=names + [NONE], required=True)})
for s, v in zip(ed["Symbol"], ed["Sheet"]):
    SS.assign[s] = "" if v == NONE else v

# ------------------------------ refresh + build ------------------------------
st.subheader("3. Refresh and build")
syms = list(SS.master)
c1, c2 = st.columns(2)
if c1.button(f"Refresh ADDSTRIKES for ALL {len(syms)} master stocks", type="primary", disabled=not syms):
    with st.spinner("Fetching option chains (this can take several minutes)…"):
        res = wg.fetch_add_strikes(syms, expiry_date=expiry, oi_threshold=SS.oi, atm_pct=SS.atm,
                                   max_workers=SS.workers, retries=SS.retries)
    SS.strikes = {**{k: v for k, v in SS.strikes.items() if k not in syms}, **res}
    SS.failed = [s for s in syms if s not in res]
    SS.fetched_at = datetime.now().strftime("%d-%b %H:%M:%S"); SS.strikes_expiry = expiry
    SS.texts = None; SS.ver += 1; st.rerun()
if SS.fetched_at:
    c1.caption(f"Last refresh {SS.fetched_at} for expiry {SS.strikes_expiry}")
    if SS.strikes_expiry != expiry:
        c1.warning("Strikes were fetched for a different expiry than the one set now. Refresh again.")
if SS.failed:
    st.warning(f"No data for {len(SS.failed)} stock(s): {', '.join(SS.failed)} → handled as “{SS.onfail}”.")
missing = [s for s in syms if s not in SS.strikes]
if missing and SS.fetched_at:
    st.info(f"{len(missing)} master stock(s) not refreshed yet: refresh again before building.")

if c2.button("Build files (validate format)"):
    if len(set(names)) != len(names) or not all(re.match(r"^[\w\- ]+$", n) for n in names):
        st.error("Sheet file names must be unique and use letters, digits, space, _ or - only.")
    else:
        out = [{**c, "stocks": [s for s in SS.master if SS.assign.get(s) == c["name"]]} for c in SS.cfg]
        try:
            SS.texts = wg.generate_watchlists(out, fetcher=lambda ss: {s: SS.strikes[s] for s in ss if s in SS.strikes},
                                              write=False, on_fail=SS.onfail, remap=SS.remap)
        except (ValueError, KeyError) as e:
            SS.texts = None; st.error(f"Format check failed, nothing built: {e}")

if SS.texts:
    st.success("All lines passed the format check. No stock appears in more than one sheet.")
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