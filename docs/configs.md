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

用于关闭 Hydra 默认输出行为并关闭 Hydra 自带的 job 日志：

- `run.dir: .` — 不创建带时间戳的输出目录
- `output_subdir: null` — 不创建 `.hydra/`
- `job.chdir: false` — 不切换工作目录
- `job_logging` — 已内置为“关闭”效果（不另打一份 process_data.log），日志由 `gem.setup_logging` 和你的 `logging.file` 控制

实验只需在 `defaults` 里写 `hydra: gem_preset`，无需再写 `override hydra/job_logging: disabled`。

## logging/default.yaml

日志默认配置（level、format、file）。实验可在主配置的 `defaults` 中引用，例如 `logging: default`，则先得到包内默认，再被 `gem_config.yaml` 等后续配置覆盖。最终 `cfg.logging` 传给 `gem.setup_logging(**cfg.logging)`。
