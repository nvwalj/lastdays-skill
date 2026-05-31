import os
import sys

# Make the engine's `lib` package importable in tests.
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "skills", "lastdays", "scripts"),
)
