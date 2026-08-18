import pandas as pd
import streamlit as st
import plotly.express as px
from module.position_fetcher_logic import PositionFetcher, Position

pf = PositionFetcher()
pos = Position(pf)

VQX_dict = {
    "VQX02": 370731921458,
    "VQX04B": 94907371893826,
    "VQX05": 370731921461,
    "VQX06": 370731921462,
    "VQX08": 370731921464,
    "VQX11": 370731921713,
    "VQX13B": 94907371959106,
    "VQX15": 370731921717,
    "VQX16A": 94907371959873,
}


#==================
# page config
#==================

st.set_page_config(
    page_title = 'Individual Server Position Details',
    layout='wide'
)

#sidebar

st.sidebar.title('Parameters')
st.sidebar.subheader('select server type')
server_type = st.sidebar.selectbox(
    'Server Type',
    ['Stocks','Index','Hybrid']
)

st.sidebar.subheader('select the server')
server= st.sidebar.selectbox(
    'select the server',
    VQX_dict.keys()
)


#header
st.title('Server Details')
col1,col2 = st.columns(2)
with col1:
    mis_match = pos.check_postion(VQX_dict[server])
    st.metric('Position',mis_match,border=True)
with col2:
    exposuer = pos.get_exposuer(VQX_dict[server])
    st.metric('Exposure (in cr)',f'{exposuer}Cr',border=True)

st.subheader('Cash by Expiry')
cash_by_exp = pos.get_cash_by_expiry(VQX_dict[server])
st.bar_chart(cash_by_exp,x='Exp Date',y='Cash',color='Cash')

st.subheader('Cash by stocks and expiry')
cash_by_stock_exp = pos.get_cash_by_stock_per_expiry(VQX_dict[server])
st.bar_chart(cash_by_stock_exp,x='Symbol',y='cash_used',color='cash_used')
