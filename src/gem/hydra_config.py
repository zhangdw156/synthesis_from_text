"""Register GEM Hydra preset configs so experiments can use them in defaults.

Call before @hydra.main in your experiment script::

    from gem import register_hydra_preset
    register_hydra_preset()

    @hydra.main(config_path="conf", config_name="config", version_base=None)
    def main(cfg):
        ...
"""

from __future__ import annotations

import logging
from importlib import resources
from typing import Any

from omegaconf import OmegaConf

logger = logging.getLogger(__name__)


def _load_package_yaml(path: str) -> dict[str, Any]:
    """Load a YAML file from the gem package (e.g. configs/hydra_preset.yaml)."""
    try:
        content = (resources.files("gem") / path).read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("Could not load gem config %s: %s", path, e)
        return {}
    return OmegaConf.create(content)


def register_hydra_preset() -> None:
    """Register the GEM Hydra preset (no output dir, no .hydra/, no chdir) with Hydra ConfigStore.

    Must be called before @hydra.main(). In your config.yaml add to defaults::

        defaults:
          - hydra: gem_preset
    """
    from hydra.core.config_store import ConfigStore

    node = _load_package_yaml("configs/hydra_preset.yaml")
    if not node:
        return
    cs = ConfigStore.instance()
    cs.store(group="hydra", name="gem_preset", node=node)
