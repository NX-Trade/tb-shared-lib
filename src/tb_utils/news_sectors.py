"""Which market sectors a news item is about, tagged with the sector indices' own symbols.

The tags are the symbols of the sector indices the Sector Rotation page shows (``NIFTYIT``,
``CNXPHRM``...), so a headline and a tile can be joined directly. Two sources, because most market
news names no stock:

* **Stocks it names.** A stock belongs to every sector index it is a constituent of (a bank is
  in the bank, private-bank and financial-services indices), and to the sector index its NSE
  sector label stands for.
* **Sector words in the text.** "pharma", "steel", "crude", "PSU banks"... A deliberately narrow
  list: it prefers missing a story to tagging a wrong one, so macro words ("RBI", "rate cut") are
  not used and "central bank" or "World Bank" do not mean the banking sector.

Pure functions, no database: the caller supplies the constituents and the sector labels
(``load_symbol_sectors`` does that from the tables).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Optional

SECTOR_MAX_LEN = 200  # news.sectors is VARCHAR(200); all 16 tags together are about 140 characters


@dataclass(frozen=True)
class Sector:
    """One taggable sector: index symbol, plain name, NSE's constituent-list names, its words."""

    symbol: str
    name: str
    index_names: tuple[str, ...]
    keywords: tuple[str, ...] = ()


SECTORS: tuple[Sector, ...] = (
    Sector(
        "BANKNIFTY",
        "Banks",
        ("Nifty Bank",),
        ("banks", "banking", "bank (nifty|stocks|shares|index)"),
    ),
    Sector(
        "CNXPSBK",
        "PSU banks",
        ("Nifty PSU Bank",),
        ("psu banks?", "public[- ]sector banks?", "psbs?"),
    ),
    Sector(
        "NIFTYPVTBA",
        "Private banks",
        ("Nifty Private Bank",),
        ("private([- ]sector)? banks?",),
    ),
    Sector(
        "NSEFIN",
        "Financial services",
        ("Nifty Financial Services",),
        (
            "nbfcs?",
            "insurers?",
            "insurance",
            "mutual funds?",
            "amcs?",
            "housing finance",
            "microfinance",
            "financial services",
            "brokerages?",
            "fintechs?",
        ),
    ),
    Sector(
        "CNXAUTO",
        "Auto",
        ("Nifty Auto",),
        (
            "autos?",
            "automobiles?",
            "automakers?",
            "car ?makers?",
            "two-?wheelers?",
            "passenger vehicles?",
            "ev makers?",
            "tractors?",
        ),
    ),
    Sector(
        "NIFTYIT",
        "IT",
        ("Nifty IT",),
        (
            "it (services|sector|stocks|firms|majors|companies|spending|exports)",
            "software (services|exports|stocks|firms)",
            "tech services",
            "nasscom",
        ),
    ),
    Sector(
        "CNXPHRM",
        "Pharma",
        ("Nifty Pharma",),
        ("pharma", "pharmaceuticals?", "us ?fda", "drug ?makers?", "generic drugs?", "api makers?"),
    ),
    Sector(
        "NIFTYHEAL",
        "Healthcare",
        ("Nifty Healthcare", "Nifty Healthcare Index"),
        ("healthcare", "health care", "hospitals?", "diagnostics?"),
    ),
    Sector(
        "CNXFMCG",
        "FMCG",
        ("Nifty FMCG",),
        ("fmcg", "consumer goods", "packaged foods?"),
    ),
    Sector(
        "CNXMET",
        "Metals",
        ("Nifty Metal",),
        ("metals?", "steel", "aluminium", "aluminum", "copper", "zinc", "iron ore", "mining"),
    ),
    Sector(
        "NIFTYOIL",
        "Oil & gas",
        ("Nifty Oil and Gas", "Nifty Oil & Gas"),
        (
            "crude",
            "brent",
            "oil (&|and) gas",
            "refiners?",
            "refiner(y|ies)",
            "petroleum",
            "natural gas",
            "lng",
            "oil marketing",
            "oil prices?",
        ),
    ),
    Sector(
        "CNXREAL",
        "Realty",
        ("Nifty Realty",),
        (
            "real estate",
            "realty",
            "housing (sales|demand|prices)",
            "property (market|prices|sales)",
            "reits?",
        ),
    ),
    Sector("CNXCEM", "Cement", (), ("cement",)),
    Sector(
        "CNXCHEM",
        "Chemicals",
        ("Nifty Chemicals",),
        ("chemicals?", "specialty chemicals?"),
    ),
    Sector(
        "CNXCD",
        "Consumer durables",
        ("Nifty Consumer Durables",),
        (
            "consumer durables?",
            "home appliances?",
            "white goods",
            "air conditioners?",
            "refrigerators?",
        ),
    ),
    Sector(
        "NIFTYMEDIA",
        "Media",
        ("Nifty Media",),
        ("media (&|and) entertainment", "broadcasters?", "ott", "multiplex(es)?", "box office"),
    ),
)

SECTOR_BY_SYMBOL = {s.symbol: s for s in SECTORS}

# NSE's own sector label on a stock (``instrument.sector``) -> the sector index that stands for it.
LABEL_TO_SECTOR: dict[str, str] = {
    "Financial Services": "NSEFIN",
    "Automobile and Auto Components": "CNXAUTO",
    "Healthcare": "NIFTYHEAL",
    "Information Technology": "NIFTYIT",
    "Fast Moving Consumer Goods": "CNXFMCG",
    "Consumer Durables": "CNXCD",
    "Metals & Mining": "CNXMET",
    "Oil Gas & Consumable Fuels": "NIFTYOIL",
    "Construction Materials": "CNXCEM",
    "Chemicals": "CNXCHEM",
    "Realty": "CNXREAL",
    "Media Entertainment & Publication": "NIFTYMEDIA",
}

# Phrases that contain a sector word but are not about the sector.
_NOT_THE_SECTOR = re.compile(
    r"\b(central banks?|world bank|reserve bank|development bank|asian development bank"
    r"|bank of (america|england|japan|canada|china)|blood banks?|food banks?|data banks?)\b",
    re.IGNORECASE,
)
_PATTERNS: dict[str, re.Pattern[str]] = {
    s.symbol: re.compile(r"\b(" + "|".join(s.keywords) + r")\b", re.IGNORECASE)
    for s in SECTORS
    if s.keywords
}


def normalise_index_name(name: str) -> str:
    """Letters and digits only, "&" read as "and", a trailing "index" dropped (NSE adds one)."""
    cleaned = re.sub(r"[^a-z0-9]", "", str(name).lower().replace("&", "and"))
    return re.sub(r"index$", "", cleaned)


def keyword_sectors(text: Optional[str]) -> set[str]:
    """The sectors whose words appear in the text."""
    if not text:
        return set()
    cleaned = _NOT_THE_SECTOR.sub(" ", text)
    return {symbol for symbol, pattern in _PATTERNS.items() if pattern.search(cleaned)}


def build_symbol_sectors(
    constituents: Iterable[tuple[str, str]], stock_labels: Iterable[tuple[str, Optional[str]]]
) -> dict[str, set[str]]:
    """Stock symbol -> sector tags, from constituents ``(index_name, symbol)`` and sector labels.

    A stock is in each sector whose index lists it, and in the sector its NSE label stands for.
    """
    by_index = {normalise_index_name(n): s.symbol for s in SECTORS for n in s.index_names}
    out: dict[str, set[str]] = {}
    for index_name, symbol in constituents:
        sector = by_index.get(normalise_index_name(index_name))
        if sector and symbol:
            out.setdefault(symbol.upper(), set()).add(sector)
    for symbol, label in stock_labels:
        sector = LABEL_TO_SECTOR.get((label or "").strip())
        if sector and symbol:
            out.setdefault(symbol.upper(), set()).add(sector)
    return out


def tag_sectors(
    headline: Optional[str],
    summary: Optional[str],
    symbols_csv: Optional[str],
    symbol_sectors: dict[str, set[str]],
) -> Optional[str]:
    """The sectors for a news item as a comma-separated string, or None when it is about none."""
    tags = keyword_sectors(f"{headline or ''}. {summary or ''}")
    for symbol in (symbols_csv or "").split(","):
        tags |= symbol_sectors.get(symbol.strip().upper(), set())
    if not tags:
        return None
    return ",".join(sorted(tags))[:SECTOR_MAX_LEN].rstrip(",")


def load_symbol_sectors(session) -> dict[str, set[str]]:  # noqa: ANN001 - a SQLAlchemy sync session
    """The stock -> sector map from the database (constituents and instrument sector labels)."""
    from tb_utils.models import (  # pylint: disable=import-outside-toplevel
        IndexConstituent,
        Instrument,
    )

    constituents = session.query(IndexConstituent.index_name, IndexConstituent.symbol).all()
    labels = (
        session.query(Instrument.symbol, Instrument.sector).filter(Instrument.is_index == 0).all()
    )
    return build_symbol_sectors(constituents, labels)
