# GEM Hydra config presets

These files are shipped with the `gem` package for use in experiments.

## hydra_preset.yaml

Disables Hydra’s default output behaviour:

- `run.dir: .` — do not create a timestamped output directory
- `output_subdir: null` — do not create `.hydra/`
- `job.chdir: false` — do not change working directory

**Use in an experiment**

1. In your script, before `@hydra.main()`:

   ```python
   from gem import register_hydra_preset
   register_hydra_preset()
   ```

2. In your Hydra config (e.g. `conf/config.yaml`), add to `defaults`:

   ```yaml
   defaults:
     - hydra: gem_preset
     - your_app_defaults
     - _self_
   ```

## logging_default.yaml

Reference only (not registered with ConfigStore). Use the same `level` / `format` / `file` structure in your app config and pass it to `gem.setup_logging(**cfg.logging)`.
