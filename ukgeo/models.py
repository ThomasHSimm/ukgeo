from dataclasses import dataclass
from typing import Optional


@dataclass
class GeoResult:
    input: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    interpreted_as: Optional[str] = None
    match_type: Optional[str] = None   # postcode | road | junction | place | unresolved
    level_resolved: Optional[int] = None  # 1=regex, 2=os_names, 3=api, 4=llm
    confidence: Optional[str] = None   # High | Medium | Low
    candidates_considered: int = 0
    notes: Optional[str] = None

    @property
    def resolved(self) -> bool:
        return self.lat is not None and self.lon is not None

    def as_dict(self) -> dict:
        return {
            "input": self.input,
            "lat": self.lat,
            "lon": self.lon,
            "interpreted_as": self.interpreted_as,
            "match_type": self.match_type,
            "level_resolved": self.level_resolved,
            "confidence": self.confidence,
            "candidates_considered": self.candidates_considered,
            "notes": self.notes,
        }
