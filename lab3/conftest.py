"""Додає папку lab3 до sys.path, щоб тести працювали з будь-якої робочої директорії."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
