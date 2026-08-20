"""Universes for Kronos paper / research tests.

SPUS100 = first 100 holdings of SPUS ETF by weight (US, USD, Sharia)
XK100   = BIST Katılım 100 from KAP (TR, TRY, Katılım) — separate market
COMMODITIES = metals priced in TRY/gram (see paper.commodities)
CRYPTO100   = top cryptocurrencies priced in USD (see paper.crypto)
SPUS50 / CRYPTO kept as aliases for older runners.
"""

from paper.commodities import COMMODITY_LABELS
from paper.crypto import CRYPTO_LABELS

# Schwab SPUS holdings (weight order), as of ~2026-08-06.
SPUS100 = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "AVGO", "MU", "TSLA", "LLY", "AMD", "XOM",
    "JNJ", "CSCO", "ABBV", "AMAT", "LRCX", "HD", "PG", "MRK", "PANW", "GEV",
    "TXN", "KLAC", "ORCL", "LIN", "IBM", "CRWD", "TMO", "SNDK", "ANET", "PEP",
    "STX", "ABT", "MRVL", "ADI", "UNP", "TJX", "GILD", "QCOM", "WELL", "BKNG",
    "CRM", "COP", "UBER", "PLD", "ISRG", "GLW", "DHR", "NOW", "VRTX", "LOW",
    "SYK", "MDT", "ADBE", "NEM", "FTNT", "ACN", "VRT", "PWR", "TT", "MMM",
    "FCX", "MCK", "EQIX", "CSX", "JCI", "CDNS", "EMR", "CMI", "CEG", "WM",
    "SHW", "ROST", "UPS", "EOG", "MDLZ", "ORLY", "ITW", "NSC", "DASH", "CL",
    "SNPS", "SLB", "REGN", "ECL", "BSX", "CTAS", "MNST", "TGT", "URI", "TEL",
    "CRH", "TER", "NUE", "LITE", "APD", "COR", "COHR", "NXPI", "FIX", "CIEN",
]

SPUS50 = SPUS100[:50]

XK100 = [
    "BINHO", "AKFYE", "ALBRK", "ALFAS", "ALTNY", "ALKLC", "ALVES", "ARDYZ", "ASELS", "ATATP",
    "BSOKE", "BEGYO", "BERA", "BIENY", "BIMAS", "BINBN", "BMSTL", "CEMZY", "CVKMD", "CWENE",
    "CANTE", "CEMTS", "CIMSA", "DAPGM", "DCTTR", "DOFRB", "EFOR", "EGGUB", "EKGYO", "ENJSA",
    "EREGL", "TEZOL", "EUPWR", "FONET", "FORMT", "FZLGY", "GENIL", "GENTS", "GEREL", "GESAN",
    "GOKNR", "GRTHO", "GUBRF", "GLRMK", "GUNDG", "GRSEL", "HRKET", "IHLGM", "IHLAS", "IMASM",
    "ISDMR", "IZFAS", "JANTS", "KRDMD", "KARSN", "KTLEV", "KATMR", "KZBGY", "KCAER", "KOPOL",
    "KBORU", "LMKDC", "LOGO", "MAGEN", "MAVI", "MEGMT", "MERCN", "MEYSU", "MPARK", "MOPAS",
    "NTGAZ", "NETCD", "OBAMS", "ORGE", "OZATD", "PASEU", "PETKM", "POLHO", "QUAGR", "RALYH",
    "RGYAS", "SAFKR", "SARKY", "SAYAS", "SDTTR", "SELEC", "SRVGY", "SNGYO", "SUNTK", "SURGY",
    "TARKM", "TKFEN", "TKNSA", "TUKAS", "TUREX", "TUPRS", "USAK", "YEOTK", "YIGIT", "ZERGY",
]

COMMODITIES = list(COMMODITY_LABELS)

CRYPTO = list(CRYPTO_LABELS)

# Backward-compatible alias used by run_alpaca_paper.py
UNIVERSE_50 = list(SPUS50)
UNIVERSE_100 = list(SPUS100)

assert len(SPUS100) == 100, len(SPUS100)
assert len(SPUS50) == 50, len(SPUS50)
assert len(set(SPUS100)) == 100, "duplicate SPUS symbols"
assert len(XK100) == 100, len(XK100)
assert len(COMMODITIES) >= 5, len(COMMODITIES)
assert len(CRYPTO) >= 100, len(CRYPTO)
