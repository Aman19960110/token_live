
"""
Watchlist generator
===================
Builds N watchlist .txt files in this exact line format

    STOCK_BASESCRIPT:SYM|CE:5|PE:35|ADDSTRIKES:2200-2300-...|REMAP%:1.00

ADDSTRIKES is refreshed from live NSE option chains using the same
`process_stock` logic as your add-strike script (OI-threshold strikes).

HOW TO EDIT
-----------
1. Change NUM_SHEETS below           -> how many files to create.
2. Edit DEFAULT_SHEETS               -> stock list / CE / PE / strike format per sheet.
3. A stock can be in only ONE sheet (enforced). MASTER LIST = master_list(sheets).
   Or edit from code / notebook:     add_stocks(sheets, "Watchlist2", ["SYM1", "SYM2"])
                                     remove_stocks(sheets, "Watchlist2", ["SYM1"])
4. Or set INTERACTIVE = True         -> asks for count and lets you add/remove stocks.

Run:  python watchlist_generator.py       (in Colab: !pip install nselib yfinance tqdm)
"""
import copy
import re
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================ USER SETTINGS ============================
EXPIRY_DATE   = "29-12-2026"   # dd-mm-yyyy, must be an expiry present in the NSE option chain
OI_THRESHOLD  = 10             # same as your original script
ATM_PCT       = 0.00           # same as your original script
MAX_WORKERS   = 10
RETRIES       = 2              # extra passes for stocks whose fetch failed
ON_FAIL       = "empty"        # "empty": keep stock, write 'ADDSTRIKES:' (blank)
                               # "skip" : drop stock from the file
REMAP         = "1.00"         # REMAP%: value (written exactly as given)
NUM_SHEETS    = 5              # how many watchlist files to create
OUTPUT_DIR    = "."            # where files are written
INTERACTIVE   = False          # True -> prompts to change sheet count / stocks
# ======================================================================

# strike_format: "auto" -> 2200, but a stock with any decimal strike is written fully as 157.50-160.00
#                 "int" -> 2200 only (error on decimals) | "decimal2" -> 2200.00 always (Watchlist5 style)
DEFAULT_SHEETS = [
    {
        "name": "Watchlist1",          # output file = Watchlist1.txt
        "ce": 5, "pe": 5,          # CE:/PE: values written on every line of this sheet
        "strike_format": "auto",    # auto | int | decimal2
        "trailing_newline": False,
        "stocks": [
            'ADANIENT', 'ASIANPAINT', 'AXISBANK', 'BAJAJ-AUTO', 'BAJAJFINSV', 'BAJFINANCE',
            'BEL', 'BHARTIARTL', 'BSE', 'DIXON', 'ETERNAL', 'HAL', 'HCLTECH', 'HDFCBANK',
            'HEROMOTOCO', 'HINDUNILVR', 'ICICIBANK', 'INDIGO', 'ITC', 'KOTAKBANK', 'LT',
            'M&M', 'MARUTI', 'MCX', 'NESTLEIND', 'NTPC', 'PERSISTENT', 'PFC', 'POLYCAB',
            'PRESTIGE', 'RECLTD', 'RELIANCE', 'SBIN', 'SUZLON', 'TCS', 'TITAN', 'TMPV',
            'TRENT', 'WIPRO'
        ],
    },
    {
        "name": "Watchlist2",          # output file = Watchlist2.txt
        "ce": 5, "pe": 5,          # CE:/PE: values written on every line of this sheet
        "strike_format": "auto",    # auto | int | decimal2
        "trailing_newline": False,
        "stocks": [
            'ABB', 'AMBUJACEM', 'APOLLOHOSP', 'ASTRAL', 'BLUESTARCO', 'BOSCHLTD',
            'BRITANNIA', 'COFORGE', 'COLPAL', 'DLF', 'DRREDDY', 'EICHERMOT', 'GMRAIRPORT',
            'HAVELLS', 'HDFCAMC', 'HDFCLIFE', 'HYUNDAI', 'ICICILIFE', 'IDEA', 'IEX',
            'KALYANKJIL', 'MAZDOCK', 'MPHASIS', 'OFSS', 'OIL', 'PAGEIND', 'PATANJALI',
            'POWERGRID', 'POWERINDIA', 'RADICO', 'SIEMENS', 'SONACOMS', 'SUNPHARMA',
            'TATAPOWER', 'TECHM', 'TIINDIA', 'UJJIVANSFB', 'VBL', 'VEDL', 'VMM', 'VOLTAS'
        ],
    },
    {
        "name": "Watchlist3",          # output file = Watchlist3.txt
        "ce": 5, "pe": 5,          # CE:/PE: values written on every line of this sheet
        "strike_format": "auto",    # auto | int | decimal2
        "trailing_newline": False,
        "stocks": [
            'ADANIGREEN', 'ADANIPORTS', 'AMBER', 'APLAPOLLO', 'ATHERENERG', 'AUBANK',
            'BANKINDIA', 'BHEL', 'BPCL', 'CAMS', 'CDSL', 'CGPOWER', 'CIPLA', 'COCHINSHIP',
            'CONCOR', 'CROMPTON', 'DABUR', 'DELHIVERY', 'DIVISLAB', 'FORCEMOT', 'FORTIS',
            'GLENMARK', 'GODREJCP', 'GODREJPROP', 'GVT&D', 'HINDALCO', 'HINDPETRO',
            'HINDZINC', 'INDUSINDBK', 'INOXWIND', 'JIOFIN', 'KEI', 'LTM', 'LUPIN',
            'MAHABANK', 'MANKIND', 'MAXHEALTH', 'NAM-INDIA', 'NAUKRI', 'NHPC', 'PIIND',
            'PREMIERENE', 'SAGILITY', 'SBICARD', 'SBILIFE', 'SHREECEM', 'SOLARINDS',
            'SWIGGY', 'ULTRACEMCO', 'WAAREEENER'
        ],
    },
    {
        "name": "Watchlist4",          # output file = Watchlist4.txt
        "ce": 5, "pe": 5,          # CE:/PE: values written on every line of this sheet
        "strike_format": "auto",    # auto | int | decimal2
        "trailing_newline": False,
        "stocks": [
            'ABCAPITAL', 'ANANDRATHI', 'ASHOKLEY', 'AUROPHARMA', 'BANDHANBNK', 'BANKBARODA',
            'BDL', 'BHARATFORG', 'BIOCON', 'CANBK', 'CHOLAFIN', 'COROMANDEL', 'CUB',
            'CUMMINSIND', 'DATAPATTNS', 'ENRIN', 'FEDERALBNK', 'GODFRYPHLP', 'IDFCFIRSTB',
            'INDUSTOWER', 'IREDA', 'JSWENERGY', 'JUBLFOOD', 'KARURVYSYA', 'LAURUSLABS',
            'LICI', 'LODHA', 'MFSL', 'MOTHERSON', 'MOTILALOFS', 'MUTHOOTFIN', 'NATIONALUM',
            'NBCC', 'PAYTM', 'PNB', 'POLICYBZR', 'SAIL', 'SHRIRAMFIN', 'SYRMA', 'TATASTEEL',
            'TVSMOTOR', 'UNOMINDA', 'YESBANK', 'ZYDUSLIFE'
        ],
    },
    {
        "name": "Watchlist5",          # output file = Watchlist5.txt
        "ce": 5, "pe": 5,          # CE:/PE: values written on every line of this sheet
        "strike_format": "auto", # auto | int | decimal2
        "trailing_newline": False,
        "stocks": [
            'BSE', 'TITAN', 'INDHOTEL', 'BLUESTARCO', 'HINDALCO', 'ATHERENERG',
            'GMRAIRPORT', 'HYUNDAI', 'VMM', 'HEROMOTOCO', 'HCLTECH', 'MAZDOCK',
            'GODFRYPHLP', 'JSWSTEEL', 'BAJAJFINSV', 'OBEROIRLTY', 'TATAPOWER', 'FORTIS',
            'PIDILITIND', 'GRASIM', 'RADICO', 'LUPIN', 'MFSL', 'EICHERMOT', 'BPCL',
            'BRITANNIA', 'SHRIRAMFIN', 'INDUSINDBK', 'CAMS', 'HAL', 'SOLARINDS', 'BDL',
            'SBILIFE', 'VBL', 'WIPRO', 'POWERINDIA', 'MAXHEALTH', 'TATASTEEL', 'TMPV',
            'COFORGE', 'DIVISLAB', 'INDIGO', 'DIXON', 'PFC', 'AMBER'
        ],
    },]

# ----------------------------------------------------------------------
# Sheet editing helpers
# ----------------------------------------------------------------------
def build_sheets(num_sheets):
    """First `num_sheets` defaults; extra sheets (if num > defaults) are created empty."""
    sheets = dedupe_sheets(copy.deepcopy(DEFAULT_SHEETS))[:num_sheets]
    for i in range(len(sheets) + 1, num_sheets + 1):
        sheets.append({"name": f"Watchlist{i}", "ce": 5, "pe": 5,
                       "strike_format": "auto", "trailing_newline": False, "stocks": []})
        print(f"NOTE: Watchlist{i} has no default list - it is empty. Add stocks with add_stocks().")
    return sheets


def master_list(sheets):
    """MASTER LIST: every unique stock across all sheets, in order of first appearance."""
    return list(dict.fromkeys(s for sh in sheets for s in sh["stocks"]))


def dedupe_sheets(sheets, announce=True):
    """A stock may live in only ONE sheet: the lowest-numbered sheet keeps it."""
    owner = {}
    for sh in sheets:
        keep = []
        for s in sh["stocks"]:
            if s in owner:
                if announce:
                    print(f"NOTE: {s} is in {owner[s]} already - removed from {sh['name']}")
            else:
                owner[s] = sh["name"]
                keep.append(s)
        sh["stocks"] = keep
    return sheets


def _find(sheets, name):
    for s in sheets:
        if s["name"] == name:
            return s
    raise KeyError(f"No sheet named {name!r}. Have: {[s['name'] for s in sheets]}")


def add_stocks(sheets, name, symbols):
    sh = _find(sheets, name)
    for sym in symbols:
        sym = sym.strip().upper()
        if sym not in sh["stocks"]:
            sh["stocks"].append(sym)


def remove_stocks(sheets, name, symbols):
    sh = _find(sheets, name)
    drop = {s.strip().upper() for s in symbols}
    sh["stocks"] = [s for s in sh["stocks"] if s not in drop]


def interactive_edit(sheets):
    try:
        n = input(f"Number of sheets [{len(sheets)}]: ").strip()
    except EOFError:
        return sheets
    if n:
        sheets = build_sheets(int(n))
    for sh in sheets:
        print(f"\n{sh['name']}: {len(sh['stocks'])} stocks (CE:{sh['ce']} PE:{sh['pe']})")
        while True:
            cmd = input("  'a SYM,SYM' add | 'r SYM,SYM' remove | 'l' list | Enter = next sheet: ").strip()
            if not cmd:
                break
            if cmd == "l":
                print("  " + ", ".join(sh["stocks"]))
            elif cmd[:2] in ("a ", "r "):
                syms = [x for x in cmd[2:].split(",") if x.strip()]
                (add_stocks if cmd[0] == "a" else remove_stocks)(sheets, sh["name"], syms)
            else:
                print("  ?")
    return sheets

# ----------------------------------------------------------------------
# ADDSTRIKES fetch  (your process_stock logic, parameterised - logic unchanged)
# ----------------------------------------------------------------------
def get_ltp(stock):
    import yfinance as yf
    try:
        return yf.Ticker(stock + ".NS").info.get("regularMarketPrice", None)
    except Exception as e:
        print(f"LTP error {stock}: {e}")
        return None


def _num(x):
    """2200.0 -> '2200', 157.5 -> '157.5' (used only for the token text)."""
    return str(int(x)) if float(x) == int(float(x)) else str(float(x))


def _on_ladder(s, step):
    q = s / step
    return abs(q - round(q)) < 1e-9


def process_stock(stock, expiry_date=None, oi_threshold=None, atm_pct=None):
    import numpy as np
    import pandas as pd
    from datetime import datetime
    from nselib import derivatives
    expiry_date = expiry_date or EXPIRY_DATE
    oi_threshold = OI_THRESHOLD if oi_threshold is None else oi_threshold
    atm_pct = ATM_PCT if atm_pct is None else atm_pct
    dt = datetime.strptime(expiry_date, "%d-%m-%Y")
    month = f"{dt.strftime('%y')}{dt.strftime('%b').upper()}"
    try:
        data = derivatives.nse_live_option_chain(stock, expiry_date)
        if data is None or data.empty:
            return None

        x = data.groupby("Expiry_Date")["Strike_Price"].unique()
        x.index = pd.to_datetime(x.index, format="%d-%b-%Y")
        x = x.sort_index()
        strike_list = x.iloc[0]
        # step between strikes: now measured on ALL strikes (decimals included), may be e.g. 2.5
        all_strikes = np.sort(pd.Series(strike_list).astype(float).dropna().unique())
        strike_diff = float(pd.Series(np.round(np.diff(all_strikes), 4)).mode()[0])
        expiry = x.index[0]

        lot_size = data.loc[data["CALLS_Ask_Qty"] != 0, "CALLS_Ask_Qty"].min()

        ltp = get_ltp(stock)
        if ltp is None or (isinstance(ltp, float) and np.isnan(ltp)):
            return None

        atm = round(round(ltp / strike_diff) * strike_diff, 2)
        lower_range = ltp * (1 - atm_pct)
        upper_range = ltp * (1 + atm_pct)

        tokens = [f"NRML|{stock}{month}FUT"]
        add_strikes = []

        def add_pair(s):
            tokens.append(f"NRML|{stock}{month}{_num(s)}CE")
            tokens.append(f"NRML|{stock}{month}{_num(s)}PE")

        in_range = data.loc[(data["Strike_Price"] >= lower_range) &
                            (data["Strike_Price"] <= upper_range), "Strike_Price"].unique()
        for s in in_range:
            if pd.isna(s):
                continue
            s = round(float(s), 2)
            add_pair(s)
            if not _on_ladder(s, strike_diff):
                add_strikes.append((stock, s))

        otm_ce = data.loc[(data["Strike_Price"] > upper_range) &
                          (data["PUTS_OI"] > oi_threshold), "Strike_Price"].unique()
        for s in otm_ce:
            if pd.isna(s):
                continue
            s = round(float(s), 2)
            add_pair(s)
            add_strikes.append((stock, s))

        otm_pe = data.loc[(data["Strike_Price"] < lower_range) &
                          (data["CALLS_OI"] > oi_threshold), "Strike_Price"].unique()
        for s in otm_pe:
            if pd.isna(s):
                continue
            s = round(float(s), 2)
            add_pair(s)
            add_strikes.append((stock, s))

        return {"symbol": stock, "strike_diff": strike_diff, "lot_size": lot_size,
                "expiry": expiry, "ltp": ltp, "atm": atm,
                "tokens": tokens, "add_strikes": add_strikes}
    except Exception as e:
        print(f"Skip {stock}: {e}")
        return None


def fetch_add_strikes(symbols, expiry_date=None, oi_threshold=None, atm_pct=None,
                      max_workers=None, retries=None):
    """-> {symbol: sorted list of strikes} for successes. Symbols that failed are absent.
    All settings can be passed explicitly (the web app does, so users never share settings)."""
    import tqdm
    max_workers = max_workers or MAX_WORKERS
    retries = RETRIES if retries is None else retries
    symbols = list(dict.fromkeys(symbols))          # unique, order kept
    out, pending = {}, symbols
    for attempt in range(1 + retries):
        if not pending:
            break
        if attempt:
            print(f"Retry pass {attempt}: {len(pending)} stock(s): {pending}")
        with ThreadPoolExecutor(max_workers=max_workers if attempt == 0 else 3) as ex:
            futs = {ex.submit(process_stock, s, expiry_date, oi_threshold, atm_pct): s for s in pending}
            for fut in tqdm.tqdm(as_completed(futs), total=len(futs), desc="processing"):
                r = fut.result()
                if r:
                    out[r["symbol"]] = sorted({round(float(s), 2) for _, s in r["add_strikes"]})
        pending = [s for s in symbols if s not in out]
    return out

# ----------------------------------------------------------------------
# Formatting + validation
# ----------------------------------------------------------------------
_NUM = {"int": r"\d+", "decimal2": r"\d+\.\d{2}"}
MODES = ("auto", "int", "decimal2")
_SYM_RE = re.compile(r"^[A-Z0-9&\-]+$")


def fmt_strike(s, mode):
    if mode == "int":
        if float(s) != int(float(s)):
            raise ValueError(f"fractional strike {s} cannot be written in 'int' format")
        return str(int(float(s)))
    if mode == "decimal2":
        return f"{float(s):.2f}"
    raise ValueError(f"unknown strike_format {mode!r}")


def line_mode(strikes, mode):
    """auto: all-whole strikes -> int (2200); any fractional strike -> every strike of that stock in 2dp (157.50)."""
    if mode == "auto":
        return "int" if all(float(s) == int(float(s)) for s in strikes) else "decimal2"
    return mode


def make_line(sym, ce, pe, strikes, mode, remap=None):
    mode = line_mode(strikes, mode)
    remap = REMAP if remap is None else remap
    vals = [float(s) for s in strikes]
    if vals != sorted(set(vals)):
        raise ValueError(f"{sym}: strikes not strictly ascending/unique: {strikes}")
    adds = "-".join(fmt_strike(s, mode) for s in vals)
    line = f"STOCK_BASESCRIPT:{sym}|CE:{ce}|PE:{pe}|ADDSTRIKES:{adds}|REMAP%:{remap}"
    n = _NUM[mode]
    pat = (rf"^STOCK_BASESCRIPT:[A-Z0-9&\-]+\|CE:\d+\|PE:\d+\|"
           rf"ADDSTRIKES:({n}(-{n})*)?\|REMAP%:\d+\.\d{{2}}$")
    if not re.match(pat, line):
        raise ValueError(f"Bad line format: {line!r}")
    return line


def validate_sheet(sh):
    seen = set()
    for sym in sh["stocks"]:
        if not _SYM_RE.match(sym):
            raise ValueError(f"{sh['name']}: invalid symbol {sym!r}")
        if sym in seen:
            raise ValueError(f"{sh['name']}: duplicate symbol {sym}")
        seen.add(sym)
    if not isinstance(sh["ce"], int) or not isinstance(sh["pe"], int):
        raise ValueError(f"{sh['name']}: ce/pe must be integers")
    if sh["strike_format"] not in MODES:
        raise ValueError(f"{sh['name']}: strike_format must be one of {MODES}")

# ----------------------------------------------------------------------
# Main entry
# ----------------------------------------------------------------------
def generate_watchlists(sheets, fetcher=fetch_add_strikes, output_dir=OUTPUT_DIR, write=True,
                        on_fail=None, remap=None):
    """Returns {sheet_name: file_text}. Nothing is written unless ALL sheets validate."""
    on_fail = on_fail or ON_FAIL
    for sh in sheets:
        validate_sheet(sh)
    owner, dups = {}, []
    for sh in sheets:
        for s in sh["stocks"]:
            if s in owner:
                dups.append(f"{s} ({owner[s]} & {sh['name']})")
            owner.setdefault(s, sh["name"])
    if dups:
        raise ValueError("stock(s) appear in more than one sheet: " + ", ".join(dups))
    all_syms = [s for sh in sheets for s in sh["stocks"]]
    strikes = fetcher(all_syms)                      # each unique symbol fetched once
    failed = [s for s in dict.fromkeys(all_syms) if s not in strikes]

    texts = {}
    for sh in sheets:
        lines = []
        for sym in sh["stocks"]:
            if sym in failed and on_fail == "skip":
                continue
            lines.append(make_line(sym, sh["ce"], sh["pe"], strikes.get(sym, []), sh["strike_format"], remap))
        texts[sh["name"]] = "\n".join(lines) + ("\n" if sh["trailing_newline"] and lines else "")

    if write:
        os.makedirs(output_dir, exist_ok=True)
        for name, txt in texts.items():
            with open(os.path.join(output_dir, f"{name}.txt"), "w", newline="\n", encoding="utf-8") as f:
                f.write(txt)
        print(f"\nWrote {len(texts)} file(s) to {os.path.abspath(output_dir)}")
    if failed:
        print(f"WARNING: no option-chain data for {len(failed)} stock(s): {failed}")
        print(f"         ON_FAIL={on_fail!r} -> " + ("written with blank ADDSTRIKES" if on_fail == "empty"
                                                  else "removed from the files"))
    return texts


def main():
    sheets = build_sheets(NUM_SHEETS)
    if INTERACTIVE:
        sheets = interactive_edit(sheets)
    return generate_watchlists(sheets)


if __name__ == "__main__":
    watchlists = main()