"""Universes for Kronos paper / research tests.

SPUS50 = first 50 holdings of SPUS ETF by weight (US, USD, Sharia)
XK100  = BIST Katılım 100 from KAP (TR, TRY, Katılım) — separate market
COMMODITIES = metals priced in TRY/gram (see paper.commodities)
CRYPTO = top cryptocurrencies priced in USD (see paper.crypto)
UNIVERSE_50 kept as alias of SPUS50 for older runners.
"""

from paper.commodities import COMMODITY_LABELS
from paper.crypto import CRYPTO_LABELS

SPUS50 = ['AAPL', 'NVDA', 'MSFT', 'GOOGL', 'AVGO', 'MU', 'LLY', 'TSLA', 'AMD', 'XOM', 'JNJ', 'ABBV', 'CSCO', 'AMAT', 'LRCX', 'PG', 'HD', 'MRK', 'GEV', 'PANW', 'TXN', 'KLAC', 'LIN', 'TMO', 'ORCL', 'IBM', 'PEP', 'ABT', 'SNDK', 'STX', 'CRWD', 'ANET', 'TJX', 'UNP', 'ADI', 'GILD', 'WELL', 'QCOM', 'MRVL', 'BKNG', 'COP', 'CRM', 'PLD', 'UBER', 'DHR', 'ISRG', 'SYK', 'VRTX', 'LOW', 'NOW']

XK100 = ['BINHO', 'AKFYE', 'ALBRK', 'ALFAS', 'ALTNY', 'ALKLC', 'ALVES', 'ARDYZ', 'ASELS', 'ATATP', 'BSOKE', 'BEGYO', 'BERA', 'BIENY', 'BIMAS', 'BINBN', 'BMSTL', 'CEMZY', 'CVKMD', 'CWENE', 'CANTE', 'CEMTS', 'CIMSA', 'DAPGM', 'DCTTR', 'DOFRB', 'EFOR', 'EGGUB', 'EKGYO', 'ENJSA', 'EREGL', 'TEZOL', 'EUPWR', 'FONET', 'FORMT', 'FZLGY', 'GENIL', 'GENTS', 'GEREL', 'GESAN', 'GOKNR', 'GRTHO', 'GUBRF', 'GLRMK', 'GUNDG', 'GRSEL', 'HRKET', 'IHLGM', 'IHLAS', 'IMASM', 'ISDMR', 'IZFAS', 'JANTS', 'KRDMD', 'KARSN', 'KTLEV', 'KATMR', 'KZBGY', 'KCAER', 'KOPOL', 'KBORU', 'LMKDC', 'LOGO', 'MAGEN', 'MAVI', 'MEGMT', 'MERCN', 'MEYSU', 'MPARK', 'MOPAS', 'NTGAZ', 'NETCD', 'OBAMS', 'ORGE', 'OZATD', 'PASEU', 'PETKM', 'POLHO', 'QUAGR', 'RALYH', 'RGYAS', 'SAFKR', 'SARKY', 'SAYAS', 'SDTTR', 'SELEC', 'SRVGY', 'SNGYO', 'SUNTK', 'SURGY', 'TARKM', 'TKFEN', 'TKNSA', 'TUKAS', 'TUREX', 'TUPRS', 'USAK', 'YEOTK', 'YIGIT', 'ZERGY']

COMMODITIES = list(COMMODITY_LABELS)

CRYPTO = list(CRYPTO_LABELS)

# Backward-compatible alias used by run_alpaca_paper.py
UNIVERSE_50 = list(SPUS50)

assert len(SPUS50) == 50, len(SPUS50)
assert len(XK100) == 100, len(XK100)
assert len(COMMODITIES) >= 5, len(COMMODITIES)
assert len(CRYPTO) >= 5, len(CRYPTO)
