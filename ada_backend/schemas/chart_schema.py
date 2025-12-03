from enum import Enum
from typing import List, Union
from pydantic import BaseModel


class Dataset(BaseModel):
    label: str
    data: List[Union[int, float, str, None]]
    borderColor: str | None = None
    backgroundColor: str | List[str] | None = None
    fill: bool | None = None


class ChartData(BaseModel):
    labels: List[Union[int, str, float]]
    datasets: List[Dataset]


class ChartType(Enum):
    LINE = "line"
    BAR = "bar"
    DOUGHNUT = "doughnut"
    RADAR = "radar"
    POLAR_AREA = "polarArea"
    SCATTER = "scatter"
    BUBBLE = "bubble"
    AREA = "area"
    CANDLESTICK = "candlestick"
    BOXPLOT = "boxplot"
    TABLE = "table"


class Chart(BaseModel):
    id: str
    type: ChartType
    title: str
    data: ChartData
    x_axis_type: str | None = None
    y_axis_type: str | None = None


class ChartsResponse(BaseModel):
    charts: List[Chart]
