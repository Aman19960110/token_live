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

## Usage

To run the application, execute the following command in your terminal:
```
streamlit run src/app.py
```

This will start a local server, and you can access the dashboard in your web browser at `http://localhost:8501`.

## Contributing

Contributions are welcome! If you have suggestions for improvements or new features, please open an issue or submit a pull request.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.
