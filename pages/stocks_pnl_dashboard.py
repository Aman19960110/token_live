import streamlit as st
import pandas as pd
import zipfile
import rarfile
import io
import plotly.express as px

# -------------------------
# Helper: process single file
# -------------------------
def process_file_content(file_bytes):
    try:
        data = pd.read_csv(
            io.BytesIO(file_bytes),
            header=None,
            names=[
                'abc','bce','symbol','cont_typ','expiry','strike','inst_type','inst_name','cef',
                'efd','id','efg','buy_sell','quantity','price','ghi','mod','id_2','hij',
                'datetime','datetime_02','xyz','pqr','stu','tqp','qwe'
            ],
            dtype=str,
            engine="python",
            on_bad_lines="skip"
        )
    except Exception as e:
        st.error(f"Failed to parse file: {e}")
        return pd.DataFrame()

    cols = ['symbol','cont_typ','expiry','strike','inst_type','inst_name','id',
            'buy_sell','quantity','price','id_2','datetime','datetime_02']
    for c in cols:
        if c not in data.columns:
            data[c] = pd.NA

    df = data[cols].copy()

    df['inst_type'] = df['inst_type'].astype(str).str.strip().str.upper()
    df['buy_sell'] = pd.to_numeric(df['buy_sell'], errors='coerce').fillna(0).astype(int)
    df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce').fillna(0).astype(int)
    df['price'] = pd.to_numeric(df['price'], errors='coerce')
    df['strike'] = pd.to_numeric(df['strike'], errors='coerce')

    df['date_str'] = df['datetime_02'].astype(str).str.extract(r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', expand=False)
    df['date'] = pd.to_datetime(df['date_str'], format="%d %b %Y", errors='coerce')

    collected_data = []

    for expiry in df['expiry'].dropna().unique():
        mask1 = df[df['expiry'] == expiry].copy()
        if mask1.empty:
            continue

        mask = mask1.groupby(['symbol','expiry','inst_type','buy_sell'], dropna=False).agg({
            'date': 'first',
            'strike': 'mean',
            'quantity': 'sum',
            'price': 'mean',
        }).reset_index()

        stock_list = mask['symbol'].dropna().unique()

        for stock in stock_list:
            data_stock = mask[mask['symbol'] == stock].copy()
            if data_stock.empty:
                continue

            xx_data = data_stock[data_stock['inst_type'] == 'XX']
            if xx_data.empty:
                continue

            for _, row in xx_data.iterrows():
                trade = None
                parity = None
                expense = None
                net_quantity = 0

                try:
                    if row['buy_sell'] == 2:  # OPEN
                        ce_row = data_stock[(data_stock['inst_type']=='CE') & (data_stock['buy_sell']==1)]
                        pe_row = data_stock[(data_stock['inst_type']=='PE') & (data_stock['buy_sell']==2)]

                        if ce_row.empty or pe_row.empty:
                            continue

                        ce_price = float(ce_row['price'].iloc[0])
                        pe_price = float(pe_row['price'].iloc[0])
                        ce_strike = float(ce_row['strike'].iloc[0])

                        parity = round(abs(ce_price - pe_price - float(row['price'])) - ce_strike, 2)
                        trade = "open"
                        net_quantity = int(pe_row['quantity'].iloc[0])

                        expense = round(
                            (ce_price * 0.00055) +
                            (pe_price * 0.001625) +
                            (float(row['price']) * 0.00028118), 2
                        )

                    else:  # CLOSE
                        ce_row = data_stock[(data_stock['inst_type']=='CE') & (data_stock['buy_sell']==2)]
                        pe_row = data_stock[(data_stock['inst_type']=='PE') & (data_stock['buy_sell']==1)]

                        if ce_row.empty or pe_row.empty:
                            continue

                        ce_price = float(ce_row['price'].iloc[0])
                        pe_price = float(pe_row['price'].iloc[0])
                        ce_strike = float(ce_row['strike'].iloc[0])

                        parity = round(-abs(-ce_price + pe_price + float(row['price'])) + ce_strike, 2)
                        trade = "close"
                        net_quantity = int(pe_row['quantity'].iloc[0])

                        expense = round(
                            (ce_price * 0.001625) +
                            (pe_price * 0.00055) +
                            (float(row['price']) * 0.00005618), 2
                        )

                    collected_data.append({
                        'date': row['date'] if not pd.isna(row['date']) else mask1['date'].iloc[0] if not mask1['date'].isna().all() else pd.NaT,
                        'expiry': expiry,
                        'stock': stock,
                        'net_quantity': net_quantity,
                        'trade': trade,
                        'parity': parity,
                        'expense': expense
                    })
                except Exception:
                    continue

    df_out = pd.DataFrame(collected_data)
    if df_out.empty:
        return df_out

    df_out['pnl'] = (df_out['parity'] - df_out['expense']) * df_out['net_quantity']
    df_out['date'] = pd.to_datetime(df_out['date'], errors='coerce')
    df_out['expiry'] = pd.to_datetime(df_out['expiry'], format="%d %b %Y", errors='coerce')
    return df_out

# -------------------------
# STREAMLIT UI
# -------------------------
st.title("📘 STOCKS CR Trade Analyzer")
st.write("Upload **.txt**, **multiple txt**, **.zip**, or **.rar** files")
st.set_page_config(layout="wide", page_title="📘 Options Trade Analyzer")

uploaded_files = st.file_uploader(
    "Upload Files",
    type=["txt", "zip", "rar"],
    accept_multiple_files=True
)

final_df = pd.DataFrame()

if uploaded_files:
    st.success(f"{len(uploaded_files)} file(s) uploaded")

    for uploaded in uploaded_files:
        try:
            file_bytes = uploaded.read()
        except Exception as e:
            st.error(f"Could not read {uploaded.name}: {e}")
            continue

        file_type = uploaded.name.split(".")[-1].lower()

        if file_type == "txt":
            st.write(f"Processing TXT → {uploaded.name}")
            df = process_file_content(file_bytes)
            if not df.empty:
                final_df = pd.concat([final_df, df], ignore_index=True)

        elif file_type == "zip":
            st.write(f"Extracting ZIP → {uploaded.name}")
            try:
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                    for name in z.namelist():
                        if name.endswith(".txt"):
                            st.write(f"Processing inside ZIP → {name}")
                            inner = z.read(name)
                            df = process_file_content(inner)
                            if not df.empty:
                                final_df = pd.concat([final_df, df], ignore_index=True)
            except Exception as e:
                st.error(f"Invalid zip file {uploaded.name}: {e}")

        elif file_type == "rar":
            st.write(f"Extracting RAR → {uploaded.name}")
            try:
                with rarfile.RarFile(fileobj=io.BytesIO(file_bytes)) as rf:
                    for info in rf.infolist():
                        name = info.filename
                        if name.endswith(".txt"):
                            st.write(f"Processing inside RAR → {name}")
                            inner = rf.read(name)
                            df = process_file_content(inner)
                            if not df.empty:
                                final_df = pd.concat([final_df, df], ignore_index=True)
            except rarfile.RarCannotExec:
                st.error("rarfile cannot find unrar/rar. Install 'unrar' to read RAR files.")
            except Exception as e:
                st.error(f"Invalid rar file {uploaded.name}: {e}")

    if final_df.empty:
        st.info("No valid data extracted.")
    else:
        st.subheader("📊 Final Output")
        display_df = final_df.copy()
        display_df['date'] = pd.to_datetime(display_df['date']).dt.date
        display_df['expiry'] = pd.to_datetime(display_df['expiry']).dt.date
        st.dataframe(display_df)

# -------------------------
# VISUALIZATIONS
# -------------------------
if not final_df.empty:

    st.subheader("🥧 Total PnL by Expiry (Plotly)")
    pnl_by_expiry = final_df.groupby("expiry", as_index=False)["pnl"].sum()
    fig = px.pie(pnl_by_expiry, names="expiry", values="pnl", title="PnL Share by Expiry", hole=0.3)
    st.plotly_chart(fig, width="stretch")

    st.subheader("📈 Cumulative PnL by Expiry")
    final_df = final_df.sort_values(["expiry", "date"])
    final_df["cumulative_pnl"] = final_df.groupby("expiry")["pnl"].cumsum()
    fig_line = px.line(final_df, x="date", y="cumulative_pnl", color="expiry",
                       title="Cumulative PnL Over Time for Each Expiry")
    st.plotly_chart(fig_line, width="stretch")

    st.subheader("Total PnL for Each Stock Across Expiries")
    df_stock = final_df.groupby(['stock', 'expiry'], as_index=False)['pnl'].sum()
    fig_stock_pnl = px.bar(df_stock, x="stock", y="pnl", color="expiry", barmode="group", text="pnl", color_discrete_sequence=px.colors.qualitative.Vivid,
                           title="Total PnL for Each Stock Across Expiries")
    fig_stock_pnl.update_traces(textposition='outside')
    st.plotly_chart(fig_stock_pnl, width="stretch")


    try:
        import pygwalker as pyg
        from pygwalker.api.streamlit import StreamlitRenderer

        st.markdown("### Use Pygwalker In Streamlit")
        renderer = StreamlitRenderer(final_df)
        renderer.explorer()
    except Exception:
        st.info("Pygwalker not available.")
