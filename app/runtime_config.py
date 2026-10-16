"""Keep downloaded models and translation packages with this installation."""
import os
from pathlib import Path

def configure():
    root = Path(__file__).resolve().parent
    values = {'ARGOS_PACKAGES_DIR': root/'translation_models',
              'XDG_DATA_HOME': root/'data', 'XDG_CONFIG_HOME': root/'config',
              'XDG_CACHE_HOME': root/'cache', 'HF_HOME': root/'cache'/'huggingface'}
    for name, path in values.items():
        path.mkdir(parents=True, exist_ok=True)
        os.environ[name] = str(path)
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
    return root
