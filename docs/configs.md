# GEM Hydra 配置预设

`src/gem/configs` 下的配置随 `gem` 包一起发布，供实验通过 **config search path** 复用。实验里无需在代码中做任何 register，只需在**主配置**中设置 `hydra.searchpath` 并在 `defaults` 中引用即可。

## 使用方式（最佳实践）

1. 在实验的**主配置**（如 `conf/config.yaml`）中设置 searchpath，并在 `defaults` 中引用所需预设：

   ```yaml
   defaults:
     - hydra: gem_preset
     - your_app_defaults
     - _self_

   hydra:
     searchpath:
       - pkg://gem.configs
   ```

2. 无需在脚本里调用任何注册函数。

Hydra 会在 `pkg://gem.configs` 对应的包目录下查找 config group，例如 `hydra: gem_preset` 对应 `hydra/gem_preset.yaml`。

## hydra/gem_preset.yaml

用于关闭 Hydra 默认输出行为（不改 job_logging）：

- `run.dir: .` — 不创建带时间戳的输出目录
- `output_subdir: null` — 不创建 `.hydra/`
- `job.chdir: false` — 不切换工作目录

文件日志由 Hydra 默认 `job_logging` 负责；控制台日志由应用侧 `setup_logging(level=..., format=...)` 负责（不传 `log_file`）。

## logging/default.yaml

日志默认配置（level、format；可选 file，仅作配置占位，应用只把 level/format 用于控制台）。实验在主配置的 `defaults` 中引用 `logging: default` 后，由 `gem_config.yaml` 等覆盖。应用仅用 `cfg.logging` 的 level、format 调用 `setup_logging(level=..., format=...)`，不向文件写日志，文件日志由 Hydra 负责。
