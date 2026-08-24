## 1. 配置加载

- [x] 1.1 在配置加载逻辑中加入 `~/.babyface/config.toml` 作为默认用户配置候选路径
- [x] 1.2 保持配置优先级为 `--config`、`BABYFACE_CONFIG_PATH`、当前目录 `babyface.toml`、用户目录配置
- [x] 1.3 增加单元测试验证当前目录无配置时会读取用户目录配置

## 2. 启动 Banner

- [x] 2.1 移除 Banner 顶部的小号 `BABYFACE` 文案
- [x] 2.2 在大号 `BABYFACE` 下方增加 `- Your Local Personal Agent -`
- [x] 2.3 让 Banner 内容在面板中水平和垂直居中
- [x] 2.4 增加单元测试验证 Banner 的关键文本和对齐结构

## 3. 文档与验证

- [x] 3.1 更新 README 中的启动、配置优先级和用户目录配置说明
- [x] 3.2 更新 `personal-agent-runtime` 主规格中的相关行为
- [x] 3.3 执行配置与 Banner 相关单元测试
- [x] 3.4 执行完整单元测试、编译检查和 OpenSpec 主规格校验
