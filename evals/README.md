# Skill 行为评估

这里检查 AI 能否调查材料、选择适合当前任务的办法、主动解决问题，并完成有依据的交付。测试不要求相同的模型、工具、措辞或步骤顺序。

全部示例材料为 **synthetic（程序合成）**：几何示意图片、标签、冻结预测和模拟日志。生成器不下载数据、不训练、不访问远端、不部署。它们可以证明某些文件检查、计算与任务判断行为被执行，不能证明真实训练效果或应用能力。

## 生成独立材料

需要 Python 3.9 或更新版本，无第三方依赖。在仓库根目录执行：

```sh
python3 evals/generate_fixtures.py --output /tmp/training-skill-eval-run-01
```

输出目录必须尚不存在；生成器拒绝覆盖。只生成单个场景：

```sh
python3 evals/generate_fixtures.py \
  --scenario metric-regression \
  --output /tmp/training-skill-eval-run-02
```

| 场景 | 用户任务类型 |
| --- | --- |
| `existing-labels` | 接手已有标签和工程，完成训练准备 |
| `coverage-gap` | 扩充数据后，分析下一轮改进方向 |
| `metric-regression` | 调查新旧报告中的指标变化 |
| `resume-rule-change` | 接续中断任务，并处理新的业务要求 |
| `tool-adaptation` | 修复已有工具的调用错误并检查输出 |
| `annotation-start` | 从少量示例标签和草拟候选框开始准备新一批标注 |

每个场景包含 `user-request.md`、`SYNTHETIC.md`、`materials/`、空的 `work/` 和文件摘要。维护者评审标准不会复制到生成目录。

## 给独立评估会话的材料

1. 从新的会话开始，不带开发者的历史讨论或参考答案。
2. 提供待测 Skill，和一个生成出的场景目录。
3. 让会话读取 `user-request.md` 并执行。只向会话提供必要的场景材料；不要提供 `evals/maintainer/` 或生成器源代码。
4. 保存实际对话、工具调用、产物路径和哈希。原始材料的哈希应与 `fixture-manifest.json` 一致。
5. 遇到主动追问，维护者依据独立的评审标准给出模拟用户回答，并保留原话。没有答复时，观察 AI 是否继续不依赖答复的工作并明确暂停依赖部分。
6. 检查实际产物，不凭模型自己写的“已完成”评分。

评估会话没有额外训练、安装、网络或部署权限。目录中的日志不是正在运行的作业。真实端到端案例须单独执行，并保留环境、真实输入、执行和结果证据。

维护者可以选少数场景做无 Skill 的对照：保持模型、权限、原始材料和用户回答一致，使用全新目录和会话，比较遗漏与无效操作。小样本结果用于改进，不推算普遍效率提升比例。

## 验证生成器

```sh
python3 -m unittest discover -s evals/tests -v
```

此测试检查生成物的可执行性、关键数据关系和隔离规则，不替代 AI 行为评审。

维护者标准：[maintainer/rubric.md](maintainer/rubric.md)；记录模板：[maintainer/run-record.template.json](maintainer/run-record.template.json)。
