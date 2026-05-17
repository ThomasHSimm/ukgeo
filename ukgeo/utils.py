"""
Shared utility functions for ukgeo.
"""

from pathlib import Path
import os


def load_env(dotenv_path: Path | str = ".env") -> None:
    """
    Load environment variables from a .env file.
    Uses python-dotenv if available, falls back to manual parsing.
    Silently does nothing if the file does not exist.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=str(dotenv_path))
    except ImportError:
        path = Path(dotenv_path)
        if not path.exists():
            return
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(
                key.strip(),
                value.strip().strip('"').strip("'")
            )


def get_env_key(name: str, required: bool = True) -> str | None:
    """
    Get an environment variable by name.
    If required=True and the variable is missing, raises a clear error.
    """
    value = os.getenv(name)
    if required and not value:
        raise EnvironmentError(
            f"{name} not set. Add it to your .env file or set it as an "
            f"environment variable before running ukgeo."
        )
    return value
