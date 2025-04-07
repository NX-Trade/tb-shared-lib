"""FII-DII Schema."""
from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from ...utils.dtu import change_date_format, str_to_date
from ...utils.enums import DateFormatEnum, FiiDiiCategoryEnum


class FiiDiiSchema(BaseModel):
    """FII-DII Schema."""

    id: Optional[str] = None
    category: str
    fii_purchase: float
    dii_purchase: float
    fii_sales: float
    dii_sales: float
    fii_net: float
    dii_net: float
    on_date: date

    @classmethod
    def from_nse_data(cls, in_data: Dict[str, Any]) -> "FiiDiiSchema":
        """Create a model from NSE data format."""
        if not in_data.get("is_nse", False):
            return cls(**in_data)

        on_date = str_to_date(in_data["on_date"], DateFormatEnum.NSE_DATE.value)
        on_date = change_date_format(on_date, DateFormatEnum.TB_DATE.value)
        return cls(
            category=FiiDiiCategoryEnum[in_data["category"].upper()].value,
            fii_purchase=float(in_data["fii_purchase"].replace(",", "")),
            dii_purchase=float(in_data["dii_purchase"].replace(",", "")),
            fii_sales=float(in_data["fii_sales"].replace(",", "")),
            dii_sales=float(in_data["dii_sales"].replace(",", "")),
            fii_net=float(in_data["fii_net"].replace(",", "")),
            dii_net=float(in_data["dii_net"].replace(",", "")),
            on_date=on_date,
        )


class FiiDiiResponseSchema(BaseModel):
    """FII-DII Response Schema."""

    fii_dii: bool = True
    possible_keys: List[str] = []
    total_items: int
    items: List[FiiDiiSchema] = []
