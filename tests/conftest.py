import sys
from pathlib import Path

# Add the project root directory to sys.path
root_dir = Path(__file__).parent.parent
sys.path.append(str(root_dir))
