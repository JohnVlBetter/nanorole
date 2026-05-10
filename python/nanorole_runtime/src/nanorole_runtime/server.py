from __future__ import annotations

from .api import create_app
from .config import load_config


config = load_config()
app = create_app(config=config)

