from dataclasses import dataclass, replace
from typing import Any, Literal

from services.citibike_service import BikeAvailability
from services.subway_service import SubwayResult


DataKey = Literal["weather", "subway", "bikes"]
WeatherPayload = dict[str, Any]


@dataclass(frozen=True)
class AppData:
    """Latest snapshots from every app data feed.

    Screens receive this superset and declare which keys they require before
    rendering. Optional sources can remain None and render a placeholder.
    """

    weather: WeatherPayload | None = None
    subway: SubwayResult | None = None
    bikes: BikeAvailability | None = None

    def has(self, key: DataKey) -> bool:
        return self.get(key) is not None

    def get(self, key: DataKey):
        if key == "weather":
            return self.weather
        if key == "subway":
            return self.subway
        if key == "bikes":
            return self.bikes
        raise KeyError(key)

    def with_update(self, key: DataKey, value) -> "AppData":
        if key == "weather":
            return replace(self, weather=value)
        if key == "subway":
            return replace(self, subway=value)
        if key == "bikes":
            return replace(self, bikes=value)
        raise KeyError(key)
