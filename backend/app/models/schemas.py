"""
Pydantic schemas for FastAPI request validation and response serialization.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ─── Enums ────────────────────────────────────────────────────────────────────

class EventTypeEnum(str, Enum):
    planned = "planned"
    unplanned = "unplanned"


class EventCauseEnum(str, Enum):
    """
    Canonical, cleaned cause vocabulary. Rare raw causes from the source data
    (test_demo, 'Fog / Low Visibility', stray casing on Debris) are folded
    into these canonical buckets by app.utils.data_cleaning.normalize_event_cause
    before they ever reach the model or this schema.
    """
    vehicle_breakdown = "vehicle_breakdown"
    accident = "accident"
    pot_holes = "pot_holes"
    construction = "construction"
    water_logging = "water_logging"
    tree_fall = "tree_fall"
    road_conditions = "road_conditions"
    congestion = "congestion"
    public_event = "public_event"
    procession = "procession"
    vip_movement = "vip_movement"
    protest = "protest"
    debris = "debris"
    others = "others"


class SeverityEnum(str, Enum):
    low = "Low"
    medium = "Medium"
    high = "High"


class StatusEnum(str, Enum):
    active = "active"
    closed = "closed"
    resolved = "resolved"


# ─── Request Schemas ──────────────────────────────────────────────────────────

class EventCreateRequest(BaseModel):
    """Used by the what-if injector to create a simulated event."""
    event_type: EventTypeEnum
    event_cause: EventCauseEnum
    latitude: float = Field(..., ge=12.5, le=13.5, description="Latitude (Bengaluru bbox)")
    longitude: float = Field(..., ge=76.8, le=78.2, description="Longitude (Bengaluru bbox)")
    endlatitude: Optional[float] = Field(default=None, ge=12.5, le=13.5)
    endlongitude: Optional[float] = Field(default=None, ge=76.8, le=78.2)
    address: Optional[str] = None
    corridor: Optional[str] = None
    police_station: Optional[str] = None
    junction: Optional[str] = None
    zone: Optional[str] = None
    veh_type: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=1000)
    start_datetime: Optional[datetime] = Field(
        default=None,
        description="ISO datetime (UTC). Defaults to now if omitted."
    )

    model_config = {"use_enum_values": True}


class FeedbackRequest(BaseModel):
    """Post-event outcome submitted by an officer — feeds the learning loop."""
    event_id: str
    actual_duration_mins: Optional[float] = Field(default=None, ge=0, le=10080)
    actual_closure_needed: Optional[bool] = None
    actual_severity: Optional[SeverityEnum] = None
    officers_deployed: Optional[int] = Field(default=None, ge=0, le=100)
    notes: Optional[str] = Field(default=None, max_length=2000)

    model_config = {"use_enum_values": True}


class ManpowerRequest(BaseModel):
    severity: SeverityEnum
    event_cause: EventCauseEnum
    requires_road_closure: bool = False
    concurrent_active_in_station: Optional[int] = Field(
        default=None, description="How many other active events the same station is handling right now"
    )

    model_config = {"use_enum_values": True}


class BarricadeRequest(BaseModel):
    latitude: float
    longitude: float
    endlatitude: Optional[float] = None
    endlongitude: Optional[float] = None
    event_cause: EventCauseEnum
    requires_road_closure: bool = False
    corridor: Optional[str] = None
    address: Optional[str] = None

    model_config = {"use_enum_values": True}


class DiversionRequest(BaseModel):
    latitude: float
    longitude: float
    endlatitude: Optional[float] = None
    endlongitude: Optional[float] = None
    max_routes: int = Field(default=3, ge=1, le=3)


class StationAllocationRequest(BaseModel):
    station_capacity: int = Field(default=10, ge=1, le=200)
    events: List[dict] = Field(
        default_factory=list,
        description="[{event_id, severity, recommended_officers}, ...]"
    )


# ─── Response Schemas ─────────────────────────────────────────────────────────

class PredictionResponse(BaseModel):
    event_id: str
    severity: str
    severity_confidence: float
    closure_probability: float
    duration_median_mins: float
    duration_lower_mins: float
    duration_upper_mins: float
    predicted_at: datetime

    model_config = {"from_attributes": True}


class EventResponse(BaseModel):
    id: str
    event_type: str
    event_cause: str
    latitude: float
    longitude: float
    endlatitude: Optional[float] = None
    endlongitude: Optional[float] = None
    address: Optional[str] = None
    corridor: Optional[str] = None
    police_station: Optional[str] = None
    junction: Optional[str] = None
    zone: Optional[str] = None
    priority: Optional[str] = None
    requires_road_closure: bool
    status: str
    veh_type: Optional[str] = None
    description: Optional[str] = None
    start_datetime: Optional[str] = None
    is_simulated: bool
    prediction: Optional[PredictionResponse] = None

    model_config = {"from_attributes": True}


class ManpowerResponse(BaseModel):
    officers: int
    supervisor_required: bool
    units: List[str]
    rationale: str
    capacity_warning: Optional[str] = None


class BarricadePoint(BaseModel):
    latitude: float
    longitude: float
    label: str
    instruction: str


class BarricadeResponse(BaseModel):
    closure_required: bool
    barricade_type: str
    points: List[BarricadePoint]
    summary: str


class DiversionRoute(BaseModel):
    rank: int
    coordinates: List[List[float]]   # [[lat, lng], ...]
    distance_km: float
    extra_distance_km: float
    estimated_minutes: float
    description: str


class DiversionResponse(BaseModel):
    baseline_distance_km: Optional[float] = None
    routes: List[DiversionRoute]
    routing_mode: str            # "osm" or "fallback"
    note: Optional[str] = None


class EventResponseCard(BaseModel):
    """The single unified artifact: forecast + all three recommendations."""
    event: EventResponse
    prediction: PredictionResponse
    manpower: ManpowerResponse
    barricade: BarricadeResponse
    diversion: DiversionResponse


class StationAllocationResponse(BaseModel):
    assignments: List[dict]
    total_demand: int
    station_capacity: int
    shortfall: int
    over_capacity: bool


# ─── Insight response schemas ─────────────────────────────────────────────────

class HourlyPatternPoint(BaseModel):
    hour: int
    count: int
    is_curfew_window: bool
    label: str


class CauseStatPoint(BaseModel):
    cause: str
    count: int
    share_pct: float
    median_duration_mins: Optional[float] = None
    closure_rate_pct: float


class CorridorStatPoint(BaseModel):
    corridor: str
    count: int
    high_severity_pct: float
    avg_closure_rate: float


class SeverityVsPriorityPoint(BaseModel):
    cause: str
    count: int
    raw_priority_high_pct: float
    ml_severity_high_pct: float
    closure_rate_pct: float
    note: str
    discrepancy: bool


class SummaryResponse(BaseModel):
    total_events: int
    active_events: int
    planned_count: int
    unplanned_count: int
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    unique_corridors: int
    unique_junctions: int
    unique_police_stations: int
    road_closure_rate_pct: float
