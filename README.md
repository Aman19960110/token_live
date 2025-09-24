# Trading Analysis Dashboard

This project is a Trading Analysis Dashboard built using Streamlit. It provides functionalities for analyzing NSE derivatives and processing POS files. Users can upload Excel files, view summaries, and visualize data through interactive charts.
[Link to dashboard](https://crtoken.streamlit.app/)

## Features

- **NSE Derivatives Analysis**: Generate stock CR tokens based on user-defined parameters such as date, expiry month, open interest threshold, and ATM range percentage.
- **POS File Dashboard**: Upload POS files in Excel format to analyze positions, calculate exposures, and visualize M2M (Mark-to-Market) values.

## Installation

To set up the project, follow these steps:

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/trading-analysis-dashboard.git
   cd trading-analysis-dashboard
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
A comprehensive Streamlit-based trading analysis dashboard for NSE (National Stock Exchange) derivatives data analysis and token generation. This application provides various tools for options trading analysis, position management, and market data visualization.

🔗 **Live Demo**: [https://crtoken.streamlit.app/](https://crtoken.streamlit.app/)

## 📋 Table of Contents

- [Features](#features)
- [Pages Overview](#pages-overview)
- [Installation](#installation)
- [Usage](#usage)
- [File Formats](#file-formats)
- [Technical Details](#technical-details)
- [Contributing](#contributing)
- [Creator](#creator)

## ✨ Features

- **Stock CR Token Generation**: Generate NRML-style tokens for NSE derivatives
- **Position Management**: Match and analyze trading positions
- **ATM Position Analysis**: At-the-money position tracking
- **Market Data Dashboard**: Comprehensive F&O Bhavcopy analysis
- **Box Performance Tracking**: Performance analysis tools
- **Settlement Tracker**: Live VWAP calculations from TradingView data

## 📊 Pages Overview

### 1. Stock CR Token Generator
**Main landing page for token generation**

- **Purpose**: Generates stock CR tokens for NSE derivatives trading strategies
- **Input**: CSV file upload (drag & drop, 200MB limit)
- **Parameters**:
  - Date selection (calendar picker)
  - Expiry month filtering
  - Open Interest (OI) threshold
  - ATM range percentage deviation
  - PE/CE direction selection
- **Output**: NRML-style tokens for trading platforms

**Key Features**:
- Filters based on expiry month, OI threshold, and ATM range
- ATM Range Percentage defines strike price inclusion (e.g., ±8% from underlying)
- High OI strikes included beyond the specified range

### 2. Position Matching
**Position reconciliation and analysis**

- **Purpose**: Match and analyze trading positions from uploaded files
- **Input**: Excel files (XLS, XLSX, CSV)
- **Functionality**: Position matching and reconciliation tools

### 3. ATM Position
**At-the-money position analysis**

- **Purpose**: Specialized analysis for at-the-money option positions
- **Input**: Excel files (XLS, XLSX, CSV)
- **Functionality**: ATM-specific position tracking and analysis

### 4. Bhavcopy Dashboard
**Comprehensive NSE F&O market analysis**

- **Purpose**: Analyze NSE F&O Bhavcopy data with interactive visualizations
- **Input Parameters**:
  - Volume/OI selection
  - Date range picker (from/to dates)
  - Stock selection dropdown
- **Features**:
  - Top stocks by traded value charts
  - Strike-wise total traded value analysis
  - Trend analysis for selected stocks
  - Interactive data visualizations
  - Option value rankings

**Note**: Currently experiencing data concatenation issues that may affect some visualizations.

### 5. Box Performance
**Trading strategy performance analysis**

- **Purpose**: Analyze box trading strategy performance
- **Input**: TXT files (drag & drop)
- **Functionality**: Performance metrics and analysis for box strategies

### 6. Settlement Tracker
**Live market data and VWAP calculation**

- **Purpose**: Track settlement prices and calculate VWAP
- **Data Source**: Live data from TradingView
- **Input**: Stock selection and exchange selection (NSE)
- **Output**: Real-time VWAP calculations

## 🚀 Installation

### Prerequisites
- Python 3.7+
- Streamlit
- pandas
- Additional dependencies (see requirements.txt)

### Setup
```bash
# Clone the repository
git clone [your-repository-url]
cd [repository-name]

# Install dependencies
pip install -r requirements.txt

# Run the application
streamlit run app.py
```

## 📖 Usage

### Token Generation
1. Navigate to the main "Stock CR Token" page
2. Select your desired date using the calendar picker
3. Configure token parameters:
   - Set expiry month filter
   - Define OI threshold
   - Set ATM range percentage
   - Choose PE/CE direction
4. Upload your CSV file (drag & drop)
5. Generate and download tokens

### Position Analysis
1. Go to "Position Matching" or "ATM Position" pages
2. Upload your Excel/CSV position file
3. Review the analysis and reconciliation results

### Market Analysis
1. Access "Bhavcopy Dashboard"
2. Select date range and stock
3. Choose between Volume or OI analysis
4. Explore interactive charts and trends

### Performance Tracking
1. Use "Box Performance" for strategy analysis
2. Upload TXT performance files
3. Use "Settlement Tracker" for live VWAP monitoring

## 📁 File Formats

### Supported File Types
- **CSV**: Token generation, position data
- **Excel (XLS/XLSX)**: Position files, trading data
- **TXT**: Performance data, box strategy results

### File Size Limits
- Maximum file size: 200MB per upload
- Drag & drop interface for easy file handling

## 🔧 Technical Details

### Data Sources
- NSE derivatives data
- TradingView live market data
- F&O Bhavcopy files

### Key Calculations
- **ATM Range Percentage**: Defines strike price inclusion radius
- **NRML Token Generation**: Creates standardized trading tokens
- **VWAP Calculation**: Volume-weighted average price from live data
- **OI Analysis**: Open interest filtering and analysis

### Architecture
- **Frontend**: Streamlit web application
- **Backend**: Python data processing
- **Deployment**: Streamlit Cloud hosting
- **Data Processing**: pandas, numpy for calculations

## 🤝 Contributing

Contributions are welcome! If you have suggestions for improvements or new features, please open an issue or submit a pull request.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

## 👨‍💻 Creator

**Created by**: [aman19960110](https://github.com/aman19960110)

---

*Trading Analysis Dashboard | Created with Streamlit*

## 📝 Notes

- Some dashboard features may experience intermittent data processing issues
- Ensure proper file formats for optimal performance
- Live data features require active internet connection
- Token generation follows NSE derivatives specifications

## 🔗 Links

- **Live Application**: https://crtoken.streamlit.app/
- **Creator's Portfolio**: https://aman19960110.github.io/

---

*This dashboard is designed for educational and analysis purposes. Please ensure compliance with all applicable trading regulations and risk management practices.*