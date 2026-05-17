import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="requests")
warnings.filterwarnings(
    "ignore",
    message="Unable to find acceptable character detection dependency.*",
    category=Warning,
    module="requests",
)

from .level2_ner import ScoringWeights  # noqa: E402
from .maps import plot_batch_summary, plot_results  # noqa: E402
from .models import GeoResult  # noqa: E402
from .pipeline import Geocoder  # noqa: E402
from .utils import get_env_key, load_env  # noqa: E402

__all__ = [
    "Geocoder",
    "GeoResult",
    "ScoringWeights",
    "load_env",
    "get_env_key",
    "plot_results",
    "plot_batch_summary",
]
__version__ = "0.4.1"
