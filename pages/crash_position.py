import streamlit as st
import pandas as pd
import zipfile
import io
from datetime import datetime
from nselib import derivatives

# ---------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------
st.set_page_config(
    page_title="F&O Position Converter",
    page_icon="📈",
    layout="wide"
)

st.title("📈 F&O Position File Generator")

# ---------------------------------------------------
# FUNCTIONS
# ---------------------------------------------------
@st.cache_data
def get_lot_size(date='15-05-2026', expiry_date=None):

    mask = derivatives.fno_bhav_copy(date)

    mask['XpryDt'] = pd.to_datetime(mask['XpryDt']).dt.strftime('%Y-%m-%d')

    lot_size = mask[
        (mask['FinInstrmTp'] == 'STF') &
        (mask['XpryDt'] == expiry_date)
    ][['TckrSymb', 'NewBrdLotQty']].reset_index(drop=True)

    return lot_size


def get_position(position_file, date='15-05-2026', expiry_date='2026-05-26'):

    data = pd.read_excel(position_file, header=1)

    lot_size = get_lot_size(date, expiry_date)

    data['Scrip'] = data['Scrip'].astype(str).str.strip()

    data = data.merge(
        lot_size,
        left_on='Scrip',
        right_on='TckrSymb',
        how='left'
    )

    data['NewBrdLotQty'] = data['NewBrdLotQty'].fillna(1)

    data['lots'] = (
        data['Net Qty'] / data['NewBrdLotQty']
    ).astype(int)

    data['Call/Put'] = data['Call/Put'].replace('FF', 'FUT')

    data['expiry'] = data['Exp Date'].dt.strftime('%y%b').str.upper()

    data['position'] = data.apply(
        lambda row:
        f"{row['Scrip']}{row['expiry']}{int(row['STK'])}{row['Call/Put']}|{row['lots']}"
        if row['Call/Put'] != 'FUT'
        else f"{row['Scrip']}{row['expiry']}{row['Call/Put']}|{row['lots']}",
        axis=1
    )

    position = {}

    expiry = data['Exp Date'].unique()

    for exp in expiry:

        mask = data[data['Exp Date'] == exp]

        position[exp] = mask[['Scrip', 'expiry', 'position']]

    return position


# ---------------------------------------------------
# SIDEBAR INPUTS
# ---------------------------------------------------
st.sidebar.header("⚙️ Inputs")

bhav_date = st.sidebar.date_input(
    "Bhav Copy Date",
    value=datetime(2026, 5, 15)
)

expiry_date = st.sidebar.date_input(
    "Expiry Date",
    value=datetime(2026, 5, 26)
)

uploaded_file = st.sidebar.file_uploader(
    "Upload Position Excel File",
    type=['xlsx']
)

generate_btn = st.sidebar.button("🚀 Generate ZIP")


# ---------------------------------------------------
# MAIN LOGIC
# ---------------------------------------------------
if generate_btn:

    if uploaded_file is None:
        st.error("Please upload the Excel file.")
        st.stop()

    try:

        bhav_date_str = bhav_date.strftime('%d-%m-%Y')
        expiry_date_str = expiry_date.strftime('%Y-%m-%d')

        with st.spinner("Generating files..."):

            data = get_position(
                uploaded_file,
                bhav_date_str,
                expiry_date_str
            )

            # ZIP in memory only
            zip_buffer = io.BytesIO()

            with zipfile.ZipFile(
                zip_buffer,
                "w",
                zipfile.ZIP_DEFLATED
            ) as zip_file:

                total_files = 0

                for i in data.keys():

                    mask = data[i]

                    for j in mask['Scrip'].unique():

                        mask_2 = mask[
                            mask['Scrip'] == j
                        ]

                        mask_2 = mask_2.sort_values(
                            by='position',
                            ascending=False
                        )

                        position_data = mask_2['position']

                        expiry_name = pd.to_datetime(
                            i
                        ).strftime('%y%b').upper()

                        filename = f"{j}{expiry_name}.txt"

                        file_content = "\n".join(
                            position_data.astype(str)
                        )

                        # Write directly to ZIP memory
                        zip_file.writestr(
                            filename,
                            file_content
                        )

                        total_files += 1

            zip_buffer.seek(0)

        st.success(
            f"✅ Successfully generated {total_files} files."
        )

        # Download ZIP directly
        st.download_button(
            label="📥 Download ZIP",
            data=zip_buffer,
            file_name="stocks.zip",
            mime="application/zip"
        )

        # Preview
        st.subheader("📋 Preview")

        preview_data = pd.concat(data.values())

        st.dataframe(
            preview_data,
            use_container_width=True
        )

    except Exception as e:
        st.error(f"❌ Error: {str(e)}")