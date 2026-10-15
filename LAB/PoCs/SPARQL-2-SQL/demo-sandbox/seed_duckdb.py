"""Create fiben_demo.duckdb: the 10-table FIBEN slice (ddl/fiben_10_tables.sql) plus seed rows.

The spec names the IBM FIBEN benchmark as the data source. FIBEN's published schema is
FIBO-derived and much wider than the spec's 10-table slice, so this PoC seeds the slice
with **illustrative** rows instead: real company names, CIK and SIC codes, tickers and
exchanges, and approximate (rounded, not audited) prices and fiscal figures. They exist
to make the compiled SQL return recognisable rows, not to be used as financial data.

    python seed_duckdb.py [path]        # default: demo-sandbox/fiben_demo.duckdb
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
DDL = HERE / "ddl" / "fiben_10_tables.sql"

COMPANY = [  # COMP_ID, COMP_NAME, CIK_CODE, SIC_CODE, COUNTRY_INC
    (1, "Alphabet Inc.", "0001652044", "7370", "US"),
    (2, "JPMorgan Chase & Co.", "0000019617", "6021", "US"),
    (3, "Apple Inc.", "0000320193", "3571", "US"),
    (4, "Microsoft Corporation", "0000789019", "7372", "US"),
    (5, "Exxon Mobil Corporation", "0000034088", "2911", "US"),
    (6, "Johnson & Johnson", "0000200406", "2834", "US"),
    (7, "Walmart Inc.", "0000104169", "5331", "US"),
    (8, "The Goldman Sachs Group, Inc.", "0000886982", "6211", "US"),
]
EXCHANGE = [(1, "NYSE", "New York Stock Exchange", "US"), (2, "NASDAQ", "Nasdaq Stock Market", "US")]
SECURITY = [  # SEC_ID, ISSUER, EXCH, SYMBOL, SEC_NAME, SEC_TYPE, LAST_PRICE
    (101, 1, 2, "GOOGL", "Alphabet Inc. Class A Common Stock", "STOCK", 165.20),
    (102, 2, 1, "JPM", "JPMorgan Chase & Co. Common Stock", "STOCK", 205.40),
    (103, 3, 2, "AAPL", "Apple Inc. Common Stock", "STOCK", 226.80),
    (104, 4, 2, "MSFT", "Microsoft Corporation Common Stock", "STOCK", 415.10),
    (105, 5, 1, "XOM", "Exxon Mobil Corporation Common Stock", "STOCK", 118.30),
    (106, 6, 1, "JNJ", "Johnson & Johnson Common Stock", "STOCK", 161.90),
    (107, 7, 1, "WMT", "Walmart Inc. Common Stock", "STOCK", 79.60),
    (108, 8, 1, "GS", "The Goldman Sachs Group, Inc. Common Stock", "STOCK", 498.70),
    (201, 2, 1, "JPM33", "JPMorgan Chase 4.25% Notes due 2033", "BOND", 97.85),
    (202, 3, None, "AAPL43", "Apple Inc. 3.85% Notes due 2043", "BOND", 88.40),
    (203, 4, None, "MSFT26", "Microsoft 2.40% Notes due 2026", "BOND", 98.95),
    (204, 5, 1, "XOM30", "Exxon Mobil 3.00% Notes due 2030", "BOND", 94.10),
    (205, 1, None, "GOOGL30", "Alphabet 1.10% Notes due 2030", "BOND", 84.60),
]
STOCK = [  # SEC_ID, SHARES_OUTSTANDING, DIVIDEND_YIELD, PE_RATIO
    (101, 5_800_000_000, 0.0048, 23.4), (102, 2_850_000_000, 0.0225, 12.1),
    (103, 15_200_000_000, 0.0044, 34.2), (104, 7_430_000_000, 0.0075, 35.6),
    (105, 4_400_000_000, 0.0321, 14.2), (106, 2_410_000_000, 0.0306, 23.9),
    (107, 8_040_000_000, 0.0104, 39.8), (108, 315_000_000, 0.0225, 15.3),
]
BOND = [  # SEC_ID, COUPON_RATE, MATURITY_DATE, CREDIT_RATING
    (201, 0.0425, "2033-10-01", "A-"), (202, 0.0385, "2043-05-04", "AA+"),
    (203, 0.0240, "2026-08-08", "AAA"), (204, 0.0300, "2030-08-16", "AA-"),
    (205, 0.0110, "2030-08-15", "AA+"),
]
CUSTOMER = [  # CUST_ID, FULL_NAME, CUST_TYPE, TAX_ID, DOMICILE
    (1, "Maria Rossi", "RETAIL", "IT-RSSMRA80A01", "IT"),
    (2, "James Okafor", "RETAIL", "US-***-**-4471", "US"),
    (3, "Nordic Pension Fund AS", "CORP", "NO-987654321", "NO"),
    (4, "Harbour Capital Partners LLC", "CORP", "US-84-1234567", "US"),
]
ACCOUNT = [  # ACC_ID, CUST_ID, ACC_NUMBER, ACC_STATUS, CURRENCY, CASH_BALANCE
    (11, 1, "BRK-000117", "ACTIVE", "EUR", 12_500.00),
    (12, 2, "BRK-000245", "ACTIVE", "USD", 3_120.55),
    (13, 3, "INS-900031", "ACTIVE", "USD", 1_250_000.00),
    (14, 4, "INS-900078", "ACTIVE", "USD", 480_200.10),
    (15, 4, "INS-900079", "CLOSED", "USD", 0.00),
]
HOLDING = [  # HOLDING_ID, ACC_ID, SEC_ID, QUANTITY, PURCHASE_PRICE, VALUATION_DATE
    (1001, 11, 103, 40, 172.50, "2026-09-30"), (1002, 11, 101, 25, 131.20, "2026-09-30"),
    (1003, 12, 102, 60, 151.00, "2026-09-30"), (1004, 13, 104, 12_000, 301.40, "2026-09-30"),
    (1005, 13, 201, 5_000, 99.10, "2026-09-30"), (1006, 13, 105, 30_000, 104.80, "2026-09-30"),
    (1007, 14, 108, 2_500, 389.00, "2026-09-30"), (1008, 14, 106, 8_000, 158.20, "2026-09-30"),
    (1009, 14, 203, 1_500, 97.30, "2026-09-30"),
]
TRADE_ORDER = [  # ORDER_ID, ACC_ID, SEC_ID, ORDER_TYPE, ORDER_QTY, LIMIT_PRICE, TRADE_DATE
    (5001, 11, 103, "BUY", 10, 225.00, "2026-10-01"), (5002, 12, 102, "SELL", 20, 207.00, "2026-10-02"),
    (5003, 13, 107, "BUY", 15_000, 79.00, "2026-10-03"), (5004, 14, 108, "SELL", 500, 500.00, "2026-10-03"),
]
FIN_REPORT = [  # REPORT_ID, COMP_ID, FISCAL_YEAR, PERIOD, REVENUE, NET_INCOME, TOTAL_ASSETS (USD, rounded)
    (1, 1, 2022, "FY", 282.8e9, 60.0e9, 365.3e9), (2, 1, 2023, "FY", 307.4e9, 73.8e9, 402.4e9),
    (3, 1, 2024, "FY", 350.0e9, 100.1e9, 450.3e9), (4, 2, 2022, "FY", 128.7e9, 37.7e9, 3665.7e9),
    (5, 2, 2023, "FY", 158.1e9, 49.6e9, 3875.4e9), (6, 2, 2024, "FY", 177.6e9, 58.5e9, 4002.8e9),
    (7, 3, 2023, "FY", 383.3e9, 97.0e9, 352.6e9), (8, 3, 2024, "FY", 391.0e9, 93.7e9, 365.0e9),
    (9, 4, 2023, "FY", 211.9e9, 72.4e9, 411.9e9), (10, 4, 2024, "FY", 245.1e9, 88.1e9, 512.2e9),
    (11, 5, 2023, "FY", 344.6e9, 36.0e9, 376.3e9), (12, 5, 2024, "FY", 339.2e9, 33.7e9, 453.5e9),
    (13, 8, 2021, "FY", 59.3e9, 21.6e9, 1463.9e9),   # before 2022: excluded by Q4's filter
]

TABLES = {"COMPANY": COMPANY, "EXCHANGE": EXCHANGE, "SECURITY": SECURITY, "STOCK": STOCK,
          "BOND": BOND, "CUSTOMER": CUSTOMER, "ACCOUNT": ACCOUNT, "HOLDING": HOLDING,
          "TRADE_ORDER": TRADE_ORDER, "FIN_REPORT": FIN_REPORT}


def seed(path: str | Path = HERE / "fiben_demo.duckdb") -> Path:
    path = Path(path)
    if path.exists():
        path.unlink()
    con = duckdb.connect(str(path))
    con.execute(DDL.read_text(encoding="utf-8"))
    for name, rows in TABLES.items():
        marks = ", ".join("?" * len(rows[0]))
        con.executemany(f'INSERT INTO "PUBLIC"."{name}" VALUES ({marks})', rows)
    con.close()
    return path


if __name__ == "__main__":
    out = seed(sys.argv[1] if len(sys.argv) > 1 else HERE / "fiben_demo.duckdb")
    con = duckdb.connect(str(out), read_only=True)
    for name in TABLES:
        n = con.execute(f'SELECT COUNT(*) FROM "PUBLIC"."{name}"').fetchone()[0]
        print(f"{name:12} {n:3} rows")
    print("wrote", out)
