"""Top-10 liquid exchange universes for Yahoo daily cache / future FT.

Each list is curated liquid names (not full board). Yahoo suffixes:
  US none | BIST .IS | HK .HK | JP .T | LSE .L | DE .DE
  KR .KS | AU .AX | IN .NS | FR .PA
"""
from __future__ import annotations

from universes.universe import SPUS100, XK100

# 1) US — SPUS100 (already Yahoo-native)
# 2) BIST — XK100 as .IS
# 3–10) major boards, ~40 liquid each

HK40 = [
    "0700.HK", "9988.HK", "3690.HK", "1810.HK", "9618.HK", "1024.HK", "2015.HK", "9868.HK",
    "0005.HK", "0939.HK", "1398.HK", "3988.HK", "2318.HK", "0883.HK", "0857.HK", "0386.HK",
    "0941.HK", "1299.HK", "0388.HK", "0001.HK", "0016.HK", "0002.HK", "0003.HK", "0011.HK",
    "0027.HK", "0066.HK", "0175.HK", "0267.HK", "0288.HK", "0669.HK", "0688.HK", "0728.HK",
    "0762.HK", "0823.HK", "0868.HK", "0960.HK", "0968.HK", "0992.HK", "1044.HK", "1109.HK",
    "1177.HK", "1211.HK", "1928.HK", "2020.HK", "2269.HK", "2313.HK", "2382.HK", "2388.HK",
    "2628.HK", "2688.HK",
]

JP40 = [
    "7203.T", "6758.T", "9984.T", "6861.T", "8306.T", "9432.T", "4063.T", "6098.T",
    "8035.T", "6981.T", "6501.T", "7267.T", "6902.T", "6367.T", "4502.T", "4503.T",
    "3382.T", "4062.T", "7974.T", "7741.T", "6594.T", "6273.T", "7011.T", "8058.T",
    "8001.T", "8002.T", "8031.T", "2914.T", "2802.T", "2503.T", "4901.T", "4911.T",
    "4568.T", "4578.T", "6869.T", "6920.T", "6857.T", "6762.T", "6954.T", "7832.T",
    "4689.T", "4755.T", "9433.T", "9434.T", "9983.T", "8267.T", "9020.T", "9022.T",
    "8801.T", "8802.T",
]

LSE40 = [
    "SHEL.L", "AZN.L", "HSBA.L", "ULVR.L", "BP.L", "GSK.L", "DGE.L", "RIO.L",
    "BATS.L", "REL.L", "LSEG.L", "NG.L", "BA.L", "RR.L", "AAL.L", "GLEN.L",
    "VOD.L", "BT-A.L", "LLOY.L", "BARC.L", "NWG.L", "STAN.L", "PRU.L", "AV.L",
    "LGEN.L", "TSCO.L", "SBRY.L", "MKS.L", "NXT.L", "IHG.L", "CPG.L", "EXPN.L",
    "AHT.L", "RKT.L", "SN.L", "SGE.L", "INF.L", "AUTO.L", "III.L", "SDR.L",
    "IMB.L", "ANTO.L", "FCIT.L", "PSH.L", "CCH.L", "WPP.L", "SMIN.L", "SVT.L",
    "UU.L", "SSE.L",
]

DE40 = [
    "SAP.DE", "SIE.DE", "ALV.DE", "DTE.DE", "MBG.DE", "BMW.DE", "VOW3.DE", "BAS.DE",
    "BAYN.DE", "MUV2.DE", "DB1.DE", "DBK.DE", "DHL.DE", "AIR.DE", "IFX.DE", "ADS.DE",
    "RWE.DE", "EOAN.DE", "HEN3.DE", "BEI.DE", "MRK.DE", "FRE.DE", "SHL.DE", "DTG.DE",
    "VNA.DE", "HNR1.DE", "PUM.DE", "ZAL.DE", "1U1.DE", "FME.DE", "CON.DE", "PAH3.DE",
    "BNR.DE", "SY1.DE", "QIA.DE", "AFX.DE", "NDA.DE", "CBK.DE", "HEI.DE", "RHM.DE",
    "MTX.DE", "ENR.DE", "G1A.DE", "TKA.DE", "LHA.DE", "SDF.DE", "WAF.DE", "HOT.DE",
    "LEG.DE", "DWNI.DE",
]

KR40 = [
    "005930.KS", "000660.KS", "373220.KS", "207940.KS", "005380.KS", "000270.KS", "068270.KS", "035420.KS",
    "035720.KS", "006400.KS", "051910.KS", "005490.KS", "105560.KS", "055550.KS", "012330.KS", "028260.KS",
    "066570.KS", "003670.KS", "096770.KS", "034730.KS", "032830.KS", "086790.KS", "015760.KS", "017670.KS",
    "003550.KS", "009150.KS", "010130.KS", "011200.KS", "018260.KS", "024110.KS", "030200.KS", "033780.KS",
    "034220.KS", "036570.KS", "042700.KS", "047050.KS", "051900.KS", "086280.KS", "090430.KS", "097950.KS",
    "128940.KS", "138040.KS", "161390.KS", "180640.KS", "247540.KS", "259960.KS", "267250.KS", "271560.KS",
    "326030.KS", "352820.KS",
]

AU40 = [
    "BHP.AX", "CBA.AX", "CSL.AX", "NAB.AX", "WBC.AX", "ANZ.AX", "MQG.AX", "WES.AX",
    "WOW.AX", "TLS.AX", "RIO.AX", "FMG.AX", "GMG.AX", "TCL.AX", "WDS.AX", "STO.AX",
    "ORG.AX", "AGL.AX", "QAN.AX", "ALL.AX", "BXB.AX", "COL.AX", "WTC.AX", "XRO.AX",
    "REA.AX", "CPU.AX", "JHX.AX", "AMC.AX", "S32.AX", "MIN.AX", "PLS.AX", "IGO.AX",
    "NST.AX", "EVN.AX", "NCM.AX", "RMD.AX", "SHL.AX", "COH.AX", "TWE.AX", "WHR.AX",
    "APA.AX", "ASX.AX", "SCG.AX", "SGP.AX", "DXS.AX", "GPT.AX", "MGR.AX", "VCX.AX",
    "IAG.AX", "QBE.AX",
]

IN40 = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "HINDUNILVR.NS", "ITC.NS", "SBIN.NS",
    "BHARTIARTL.NS", "KOTAKBANK.NS", "LT.NS", "AXISBANK.NS", "BAJFINANCE.NS", "ASIANPAINT.NS", "MARUTI.NS", "SUNPHARMA.NS",
    "TITAN.NS", "ULTRACEMCO.NS", "WIPRO.NS", "NESTLEIND.NS", "HCLTECH.NS", "POWERGRID.NS", "NTPC.NS", "ONGC.NS",
    "TATAMOTORS.NS", "TATASTEEL.NS", "JSWSTEEL.NS", "ADANIENT.NS", "ADANIPORTS.NS", "COALINDIA.NS", "BPCL.NS", "IOC.NS",
    "INDUSINDBK.NS", "BAJAJFINSV.NS", "TECHM.NS", "CIPLA.NS", "DRREDDY.NS", "DIVISLAB.NS", "EICHERMOT.NS", "HEROMOTOCO.NS",
    "BAJAJ-AUTO.NS", "M&M.NS", "GRASIM.NS", "HINDALCO.NS", "VEDL.NS", "APOLLOHOSP.NS", "BRITANNIA.NS", "DABUR.NS",
    "PIDILITIND.NS", "GODREJCP.NS",
]

PA40 = [
    "MC.PA", "OR.PA", "AIR.PA", "SAN.PA", "TTE.PA", "BN.PA", "SU.PA", "AI.PA",
    "BNP.PA", "CS.PA", "DG.PA", "EL.PA", "EN.PA", "ENGI.PA", "GLE.PA", "HO.PA",
    "KER.PA", "LR.PA", "ML.PA", "ORA.PA", "PUB.PA", "RI.PA", "RNO.PA", "SAF.PA",
    "SGO.PA", "STLAP.PA", "STM.PA", "TEP.PA", "VIE.PA", "VIV.PA", "CAP.PA", "ACA.PA",
    "AC.PA", "ATO.PA", "CA.PA", "DSY.PA", "ERF.PA", "FR.PA", "DIM.PA", "RMS.PA",
    "WLN.PA", "URW.PA", "CO.PA", "SW.PA", "EDEN.PA", "AM.PA", "BOL.PA", "SK.PA",
    "ENX.PA", "GET.PA",
]

EXCHANGES: dict[str, dict] = {
    "us": {
        "name": "US (NYSE/Nasdaq liquid)",
        "yahoo_symbols": list(SPUS100),
        "cache_id": "spus",
    },
    "bist": {
        "name": "Borsa Istanbul (XK100)",
        "yahoo_symbols": [f"{t}.IS" for t in XK100],
        "cache_id": "xk100",
    },
    "hk": {
        "name": "Hong Kong",
        "yahoo_symbols": list(HK40),
        "cache_id": "hk",
    },
    "jp": {
        "name": "Japan (TSE)",
        "yahoo_symbols": list(JP40),
        "cache_id": "jp",
    },
    "lse": {
        "name": "London",
        "yahoo_symbols": list(LSE40),
        "cache_id": "lse",
    },
    "de": {
        "name": "Germany (Xetra)",
        "yahoo_symbols": list(DE40),
        "cache_id": "de",
    },
    "kr": {
        "name": "Korea",
        "yahoo_symbols": list(KR40),
        "cache_id": "kr",
    },
    "au": {
        "name": "Australia",
        "yahoo_symbols": list(AU40),
        "cache_id": "au",
    },
    "in": {
        "name": "India (NSE)",
        "yahoo_symbols": list(IN40),
        "cache_id": "in",
    },
    "fr": {
        "name": "France (Euronext Paris)",
        "yahoo_symbols": list(PA40),
        "cache_id": "fr",
    },
}

TOP10_IDS = list(EXCHANGES.keys())


def all_exchange_symbols() -> list[tuple[str, str]]:
    """[(cache_id, yahoo_symbol), ...]"""
    out: list[tuple[str, str]] = []
    for ex in EXCHANGES.values():
        cid = ex["cache_id"]
        for s in ex["yahoo_symbols"]:
            out.append((cid, s))
    return out
