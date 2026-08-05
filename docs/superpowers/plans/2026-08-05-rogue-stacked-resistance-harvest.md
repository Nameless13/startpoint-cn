# 叠层抗性与官方素材采集实施计划

1. 固化逆向证据：终始之龙 reset/preaction/debuff_delete 树形、
   `ACToleranceOfDebuff` 累加与命中公式、普通驱散边界。
2. 先写失败测试：叠层词条/DSL、跨族可解性、采集器 synthetic store、
   high_mobility loader 与组合门禁。
3. 在 `wf_rogue_build.py` 增加叠层数据模型、深度排程、随机池条目，扩展 c109 DSL
   生成器与 program 签名。
4. 将叠层合计纳入 `immunity_axes`，并让钉选叠层词条参与 HP 重排载体偏好。
5. 新增 `wf_boss_buff_harvest.py`，实现只读解析、标准 boss 资源解析、action 发现与
   归一化 JSON 输出。
6. 在 `rogue_special_bosses.json` 加 `high_mobility`，实现严格 loader、最终 boss
   前缀判定、时限/高档元素墙/HP 1.5 倍门禁和后置断言。
7. 打印 DSL，运行定向测试、全量 rogue 测试、30 层 dry-run 与现有塔 `--check`。
8. 在 `mod-tools/work/codex_out/` 写结果报告，单列没有通用阶段触发器的边界。
