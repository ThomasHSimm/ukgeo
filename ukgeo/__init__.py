import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="requests")
warnings.filterwarnings(
    "ignore",
    message="Unable to find acceptable character detection dependency.*",
    category=Warning,
    module="requests",
)

from .pipeline import Geocoder
from .models import GeoResult
from .level2_ner import ScoringWeights
from .utils import load_env, get_env_key

__all__ = ["Geocoder", "GeoResult", "ScoringWeights", "load_env", "get_env_key"]
__version__ = "0.3.0"
