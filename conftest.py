"""
Root conftest.py — adds src/ to sys.path so `app.*` imports work
when running pytest from the project root.
"""

import sys
import os

# Insert the src/ directory at the front of the module search path.
# This allows `import app.models`, `from app.database import ...` etc.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
