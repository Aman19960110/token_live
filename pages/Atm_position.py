import pandas as pd
import streamlit as st
import openpyxl

# Title and Header
st.title("AT Money Position")
st.header("Upload POS File (Excel)")

# Mode Selection
mode = st.radio(
    "Select ATM Calculation Mode",
    options=["Absolute Range", "Percentage"],
    help="Choose whether ATM is calculated using fixed points or percentage of futures price"
)

# Dynamic Input based on mode
if mode == "Absolute Range":
    atm_value = st.slider(
        "Select ATM Range (± points)",
        min_value=1,
        max_value=100,
        value=5,
        help="Options within this many points of futures LTP are considered ATM"
    )
else:
    atm_value = st.slider(
        "Select ATM Range (%)",
        min_value=0.1,
        max_value=5.0,
        value=0.5,
        step=0.1,
        help="Options within this % of futures LTP are considered ATM"
    )

def parse_pos_contents(file, atm_value, mode):
    try:
        # Read file
        data = pd.read_excel(file, header=1, index_col=0)
        st.success("Successfully read POS file!")

        # Required columns check
        required_columns = {'Call/Put', 'Scrip', 'STK', 'LTP', 'Net Qty'}
        if not required_columns.issubset(data.columns):
            st.error(f"Missing required columns: {required_columns - set(data.columns)}")
            return None

        # Filter active positions
        data = data[data['Net Qty'] != 0]

        # Separate Futures and Options
        fut = data[data['Call/Put'] == 'FF']
        opt = data[data['Call/Put'] != 'FF']

        # Empty ATM DataFrame
        ATM = pd.DataFrame(columns=opt.columns)

        # Loop through options
        for _, row in opt.iterrows():
            matching_fut = fut[fut['Scrip'] == row['Scrip']]

            if not matching_fut.empty:
                ltp_value = matching_fut['LTP'].values[0]

                # Threshold calculation
                if mode == "Absolute Range":
                    threshold = atm_value
                else:
                    threshold = ltp_value * (atm_value / 100)

                # ATM condition
                if abs(row['STK'] - ltp_value) < threshold:

                    # OTM logic (your original condition preserved)
                    if (
                        (row['STK'] < ltp_value and row['Call/Put'] == 'CE') or
                        (row['STK'] > ltp_value and row['Call/Put'] == 'PE')
                    ):
                        ATM = pd.concat(
                            [ATM, pd.DataFrame([row.values], columns=ATM.columns)],
                            ignore_index=True
                        )

        # Display Results
        if not ATM.empty:
            ATM = ATM[['Scrip', 'Call/Put', 'Exp Date', 'STK', 'Net Qty']]

            with st.expander("At Money Position", expanded=True):
                st.dataframe(ATM)

                # Download button
                csv = ATM.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download ATM Data as CSV",
                    data=csv,
                    file_name="atm_positions.csv",
                    mime="text/csv",
                )
        else:
            if mode == "Absolute Range":
                st.warning(f"No ATM options found within ±{atm_value} points.")
            else:
                st.warning(f"No ATM options found within ±{atm_value}% of future price.")

    except Exception as e:
        st.error(f"Error parsing POS file: {str(e)}")
        return None


# File uploader
uploaded_file = st.file_uploader(
    "Drag and Drop or Select POS File",
    type=["xls", "xlsx", "csv"],
    key="pos_file_uploader"
)

# Run processing
if uploaded_file is not None:
    parse_pos_contents(uploaded_file, atm_value, mode)
else:
    st.info("Please upload a POS Excel file.")