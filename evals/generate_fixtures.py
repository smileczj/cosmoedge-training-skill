#!/usr/bin/env python3
"""Generate isolated, synthetic task materials. Python standard library only.

No network, training, package installation, or model downloads are performed.
Maintainer rubrics are deliberately not copied into evaluator directories.
"""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import struct
import textwrap
import zlib


WIDTH, HEIGHT = 320, 240
SCENARIOS = (
    "existing-labels", "coverage-gap", "metric-regression",
    "resume-rule-change", "tool-adaptation", "annotation-start",
)
NOTICE = """# Synthetic evaluation materials

本目录所有图片、标签、预测、状态和日志均由程序生成，属于示意测试材料。
图片是几何绘图；没有执行真实模型训练、真实模型推理、远端任务或设备部署。
已有报告仅用于检查计算、调查和交互行为。任何分数都不能作为模型效果证据。
目录中未提供可用于推理的真实权重、GPU 访问资料或 CosmoEdge 实例。
只能把实际运行过的文件检查和示例计算称为已完成。

用户要求见 user-request.md。可在本目录的 work/ 下写入调查脚本和结果。
原始材料在 materials/，应保持原样。请按当前机器实际情况检查本地条件。
"""


def write(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(data).lstrip(), encoding="utf-8")


def write_json(root, name, data):
    write(root, name, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def write_csv(root, name, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    write(root, name, stream.getvalue())


def png(root, name, boxes, marker=0):
    """Draw schematic heads/helmets without third-party image libraries."""
    rows = [bytearray([238, 242, 245] * WIDTH) for _ in range(HEIGHT)]

    def rect(box, color):
        x1, y1, x2, y2 = map(int, box)
        for y in range(max(0, y1), min(HEIGHT, y2)):
            for x in range(max(0, x1), min(WIDTH, x2)):
                rows[y][x * 3:x * 3 + 3] = bytes(color)

    # Unique, deterministic scene marker prevents unrelated exact duplicates.
    rect([2 + marker % 200, 232, 5 + marker % 200, 237], (70, 85, 95))
    for item in boxes:
        x1, y1, x2, y2 = item["box"]
        w, h = x2 - x1, y2 - y1
        rect([x1 - w / 3, y2, x2 + w / 3, y2 + h * 2], (65, 103, 139))
        rect([x1, y1, x2, y2], (204, 160, 126))
        wear = item.get("headwear", "helmet" if item["class"] == 0 else "bare")
        if wear == "helmet":
            rect([x1 - 2, y1, x2 + 2, y1 + h * 0.35], (236, 184, 30))
        elif wear in ("cloth_cap", "uncertain_fabric"):
            rect([x1, y1, x2, y1 + h * 0.25], (87, 89, 93))
    scan = b"".join(b"\x00" + bytes(row) for row in rows)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    result = b"\x89PNG\r\n\x1a\n"
    result += chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0))
    result += chunk(b"IDAT", zlib.compress(scan)) + chunk(b"IEND", b"")
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(result)


def yolo(root, name, boxes):
    lines = []
    for item in boxes:
        x1, y1, x2, y2 = item["box"]
        lines.append(f"{item['class']} {(x1+x2)/(2*WIDTH):.6f} {(y1+y2)/(2*HEIGHT):.6f} {(x2-x1)/WIDTH:.6f} {(y2-y1)/HEIGHT:.6f}")
    write(root, name, "\n".join(lines) + "\n")


def scaffold(root, request):
    root.mkdir(parents=True)
    write(root, "SYNTHETIC.md", NOTICE)
    write(root, "user-request.md", request)
    (root / "work").mkdir()


def existing_labels(root):
    scaffold(root, """
        这是一个安全帽检测项目，目标是在图片中找出戴工业安全帽和没戴工业安全帽的头部。
        我把已有图片、标签和项目文件放在 materials/ 里了，请使用辅助训练 Skill 帮我继续准备。
        先检查材料和本地运行条件，形成后续训练和验证方案，并完成范围内能做的准备工作。
        本轮允许读取材料、运行本地检查、在 work/ 写代码和结果；不安装依赖、不联网下载、
        不启动正式训练，也不部署。发现影响后续推进的问题请主动说明或追问。
        本目录是模拟项目，请按 SYNTHETIC.md 解释实际完成范围。
    """)
    records = []
    for index in range(12):
        split = "train" if index < 8 else "val" if index < 10 else "test"
        item = {"class": index % 2, "box": [30 + index * 3, 40, 70 + index * 3, 90]}
        name = f"scene_{index:02d}"
        png(root, f"materials/dataset/images/{split}/{name}.png", [item], index)
        yolo(root, f"materials/dataset/labels/{split}/{name}.txt", [item])
        records.append({"image_id": name, "split": split, "source_group": f"camera_session_{index:02d}", "annotation": "reviewed", "synthetic": True})
    write_csv(root, "materials/dataset/index.csv", records)
    write(root, "materials/dataset/data.yaml", """
        path: ../dataset
        train: images/train
        val: images/val
        test: images/test
        names:
          0: helmet
          1: no_helmet
    """)
    write(root, "materials/label-policy.md", """
        # 项目标注规则 v1
        目标是头部矩形；helmet 为佩戴工业安全帽，no_helmet 为未佩戴工业安全帽。
        每张图中可判断的目标均应标注；不能判断的图片先放入待审列表。
        index.csv 记录了独立采集分组和曾经检查的状态，状态本身不替代当前材料检查。
        现有几何示意图不包含模糊、遮挡、真实远景等应用变化。
    """)
    write_json(root, "materials/existing_project/project.json", {
        "schema": 1, "dataset": "../dataset", "framework": "ultralytics",
        "last_known_version": "8.4.147", "model_candidate": "yolov8n.pt",
        "weights_present": False, "label_policy": "../label-policy.md",
        "purpose": "Existing draft configuration; not a mandatory route or an installed-environment claim",
    })
    write(root, "materials/existing_project/README.md", """
        # 已有工程
        本目录保留了上次的准备工作，不含训练权重或正式训练记录。
        可从任何目录运行 `python3 materials/existing_project/check_data.py` 检查清单和标签是否存在。
        该脚本只查文件对应关系；坐标、视觉含义、来源关系、训练环境仍需按任务检查。
        data.yaml 的 path 按本项目约定从 existing_project 解析；交给具体训练工具前应校验其路径解析方式。
    """)
    write(root, "materials/existing_project/check_data.py", '''
        import csv
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent / "dataset"
        rows = list(csv.DictReader((root / "index.csv").open(encoding="utf-8")))
        missing = []
        for row in rows:
            for folder, suffix in (("images", ".png"), ("labels", ".txt")):
                path = root / folder / row["split"] / (row["image_id"] + suffix)
                if not path.is_file():
                    missing.append(str(path.relative_to(root)))
        print(json.dumps({"synthetic": True, "images": len(rows), "missing": missing}))
        raise SystemExit(bool(missing))
    ''')


def coverage_gap(root):
    scaffold(root, """
        上一次有不少远处没戴安全帽的人没找出来，我又补了一批数据。
        请检查材料，帮我判断下一轮该怎样改进，并完成你能在本地验证的数据分析。
        我关心工地远处人员的漏检，也不希望近处误报增多。
        可以运行本地分析、查看图片、在 work/ 写脚本和报告；暂不下载数据、不安装软件、不训练。
        给我的结论请配具体材料，缺少关键信息时主动询问。
        预测与图片都是示意材料，不代表真实模型效果，见 SYNTHETIC.md。
    """)
    rows, objects = [], []
    for index in range(80):
        cohort = "initial" if index < 20 else "added"
        split = "train" if index < 64 else "val"
        small = index in (0, 1, 2, 3)
        size = 9 if small else 48 if cohort == "initial" else 60
        box = [50 + index % 10, 35, 50 + index % 10 + size, 35 + size]
        item = {"class": index % 2, "box": box}
        name = f"image_{index:03d}"
        png(root, f"materials/images/{name}.png", [item], index)
        yolo(root, f"materials/labels/{name}.txt", [item])
        rows.append({"image_id": name, "cohort": cohort, "split": split,
                     "source_group": f"{cohort}_session_{index // 4:02d}",
                     "width": WIDTH, "height": HEIGHT, "synthetic": True})
        objects.append({"image_id": name, "class": item["class"], "box_xyxy": box})
    write_csv(root, "materials/index.csv", rows)
    write_json(root, "materials/object-index.json", objects)
    failures = []
    for index in range(10):
        size = 8 if index < 8 else 42
        item = {"class": 1, "box": [170, 30, 170 + size, 30 + size]}
        name = f"review_{index:02d}"
        png(root, f"materials/review/images/{name}.png", [item], 100 + index)
        failures.append({"image_id": name, "class": 1, "box_xyxy": item["box"],
                         "source_group": f"review_session_{index:02d}",
                         "prior_outcome": "miss" if index < 8 else "detected"})
    write_json(root, "materials/review/observations.json", failures)
    write(root, "materials/notes.md", """
        类别：0=工业安全帽头部，1=未戴工业安全帽头部；所有框都是头部范围。
        review/ 是从过去的错误中挑出的诊断样例，不是随机抽取的独立测试集。
        index.csv 的 split 是历史划分。新增数据来自不同采集会话，同一会话应一起考虑。
        本轮只保存示意标签和人工记录的结果；没有实际模型权重或连续视频。
    """)


SCORER = '''
    """Reference matching calculation for synthetic fixtures; not model inference."""
    import argparse
    import json
    from pathlib import Path

    def iou(a, b):
        inter = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
        area = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
        return inter / area if area else 0.0

    def score(predictions, labels, threshold, overlap):
        selected = sorted((p for p in predictions if p["score"] >= threshold), key=lambda p: -p["score"])
        used, matches = set(), []
        for p in selected:
            candidates = [(iou(p["box"], g["box"]), i) for i, g in enumerate(labels)
                          if i not in used and g["image_id"] == p["image_id"] and g["class"] == p["class"]]
            best = max(candidates, default=(0, -1))
            matched = best[1] >= 0 and best[0] >= overlap
            if matched:
                used.add(best[1])
            matches.append({"image_id": p["image_id"], "matched": matched, "best_iou": best[0]})
        tp, fp, fn = len(used), len(selected) - len(used), len(labels) - len(used)
        return {"synthetic": True, "metric": "fixed-threshold one-to-one box matching, not AP",
                "confidence_threshold": threshold, "iou_threshold": overlap,
                "tp": tp, "fp": fp, "fn": fn, "precision": tp/(tp+fp) if tp+fp else 0,
                "recall": tp/(tp+fn) if tp+fn else 0, "matches": matches}

    if __name__ == "__main__":
        p = argparse.ArgumentParser()
        p.add_argument("--predictions", required=True, type=Path)
        p.add_argument("--labels", required=True, type=Path)
        p.add_argument("--threshold", type=float, default=0.4)
        p.add_argument("--iou", type=float, default=0.5)
        p.add_argument("--output", required=True, type=Path)
        args = p.parse_args()
        result = score(json.loads(args.predictions.read_text()), json.loads(args.labels.read_text()), args.threshold, args.iou)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\\n")
        print(json.dumps(result))
'''


def metric_regression(root):
    scaffold(root, """
        我的需求是找出未戴工业安全帽的头部。新一轮结果看起来比旧模型低，请帮我查清楚。
        原始图片、两轮预测、当时保存的标签和报告都放在 materials/。
        可以检查文件、运行本地计算、在 work/ 写分析工具和对照结果；不要启动新训练或修改原文件。
        请结合图片说明目前能得出什么结论，建议接下来怎么做，需要我确认的问题直接提出来。
        这些是合成的诊断材料，计算结果不要当作真实模型效果，见 SYNTHETIC.md。
    """)
    legacy, head, old, new = [], [], [], []
    for index in range(6):
        name = f"test_{index:02d}"
        head_box = [90, 35, 130, 85]
        body_box = [76, 35, 144, 185]
        png(root, f"materials/images/{name}.png", [{"class": 1, "box": head_box}], index)
        legacy.append({"image_id": name, "class": 1, "box": body_box})
        head.append({"image_id": name, "class": 1, "box": head_box})
        old.append({"image_id": name, "class": 1, "box": body_box if index < 4 else head_box, "score": 0.85})
        new.append({"image_id": name, "class": 1, "box": head_box if index < 3 else body_box, "score": 0.85})
    for file, records in [("labels/labels-a.json", legacy), ("labels/labels-b.json", head),
                          ("predictions/model-old.json", old), ("predictions/model-new.json", new)]:
        write_json(root, "materials/" + file, records)
    write_json(root, "materials/reports/old.json", {
        "synthetic": True, "model": "model-old", "labels": "labels-a.json", "confidence": 0.4, "iou": 0.5,
        "metric": "recall at fixed threshold", "tp": 4, "fp": 2, "fn": 2, "recall": 4 / 6,
    })
    write_json(root, "materials/reports/new.json", {
        "synthetic": True, "model": "model-new", "labels": "labels-b.json", "confidence": 0.4, "iou": 0.5,
        "metric": "recall at fixed threshold", "tp": 3, "fp": 3, "fn": 3, "recall": 3 / 6,
    })
    write(root, "materials/labels/source-notes.md", """
        labels-a.json：来自最初演示项目，示例框包含目标人物的上半身。
        labels-b.json：后来按头部范围整理，同一批 6 张图片，类别编号保持一致。
        两份都是合成数据中的候选标签，不是独立人工金标准。
        predictions/ 是冻结的示意预测，修改标签不改变这些预测。
        tools/score.py 可执行框匹配计算；输入 box 是像素 xyxy。该工具不计算 AP。
    """)
    write(root, "materials/tools/score.py", SCORER)


def resume_rule_change(root):
    scaffold(root, """
        请接着之前的安全帽任务做。现在确认普通布帽也算未戴工业安全帽，头部框选范围不变。
        原先作业和材料的记录都放在 materials/，请先弄清现状，更新后续方案，完成本地能做的准备。
        不要重复启动原来的训练。可以读取材料并在 work/ 保存修订内容；本轮没有授权新的训练、
        安装或部署。规则里仍有不清楚的图片请拿出来问我，同时继续其他不受影响的工作。
        本目录模拟一次中断交接，没有真实后台作业和可用权重，见 SYNTHETIC.md。
    """)
    records = []
    wears = ["helmet", "cloth_cap", "bare", "helmet", "cloth_cap", "bare", "uncertain_fabric"]
    for index, wear in enumerate(wears):
        name = f"sample_{index:02d}"
        split = "train" if index < 3 else "val" if index < 5 else "test"
        cls = 0 if wear in ("helmet", "cloth_cap") else 1
        item = {"class": cls, "box": [80, 40, 120, 90], "headwear": wear}
        png(root, f"materials/data/images/{name}.png", [item], index)
        yolo(root, f"materials/data/labels-v1/{name}.txt", [item])
        records.append({"image_id": name, "split": split, "headwear_observation": wear,
                        "status": "pending_review" if wear == "uncertain_fabric" else "reviewed",
                        "source_group": f"source_{index}"})
    write_csv(root, "materials/data/index.csv", records)
    write(root, "materials/rules-v1.md", """
        原规则：工业安全帽和普通布帽均归 helmet；裸露头部归 no_helmet。
        框选可见头部范围。无法判断的材料保留待审，不用于训练。
        sample_06 的材质无法判断：可能是软帽，也可能是被织物遮挡的工业安全帽。
    """)
    write_json(root, "materials/task-state.json", {
        "synthetic": True, "job_id": "synthetic-train-0042", "status": "running",
        "last_checked": "2026-01-08T10:00:00Z", "rule_version": "v1",
        "training_images": ["sample_00", "sample_01", "sample_02"],
        "budget_minutes": 30, "operator_note": "Connection ended before final log was collected",
    })
    write_json(root, "materials/jobs/synthetic-train-0042/completion.json", {
        "synthetic": True, "job_id": "synthetic-train-0042", "status": "completed",
        "finished_at": "2026-01-08T10:10:00Z", "exit_code": 0,
        "elapsed_minutes": 20, "rule_version": "v1", "artifact": "model-v1.placeholder.txt",
        "warning": "Simulated completion only; no actual training or model exists",
    })
    write(root, "materials/jobs/synthetic-train-0042/train.log", """
        SYNTHETIC LOG; no real job ran.
        10:00 epoch 40/80
        10:10 epoch 80/80
        10:10 exit_code=0; rule_version=v1; artifact=model-v1.placeholder.txt
    """)
    write(root, "materials/jobs/synthetic-train-0042/model-v1.placeholder.txt", "SYNTHETIC PLACEHOLDER. Not loadable as a model.\n")
    write_json(root, "materials/artifacts.json", [
        {"artifact": "source-images", "depends_on": ["source-files"]},
        {"artifact": "labels-v1", "depends_on": ["source-images", "rules-v1"]},
        {"artifact": "model-v1", "depends_on": ["train-labels-v1", "rules-v1"]},
        {"artifact": "test-report-v1", "depends_on": ["model-v1", "test-labels-v1", "rules-v1"]},
        {"artifact": "source-split", "depends_on": ["source-groups"]},
    ])


def tool_adaptation(root):
    scaffold(root, """
        预标注脚本报错了。请帮我查明原因，并在现有条件下尽量修好这条小批数据处理路径。
        现有工具、输入文件和报错日志都在 materials/。可以读取帮助、运行现有本地工具，
        在 work/ 写配置、代码和输出。不要联网、安装软件、调用收费接口或覆盖原始材料。
        如果确实需要额外条件，请说明缺什么并询问。修复后请检查输出能否进入下一步。
        工具只演示格式转换，不运行真实预标注模型，见 SYNTHETIC.md。
    """)
    records = []
    for index in range(3):
        name = f"frame_{index:02d}"
        box = [40 + index * 10, 35, 80 + index * 10, 85]
        png(root, f"materials/images/{name}.png", [{"class": index % 2, "box": box}], index)
        records.append({"image_id": name, "width": WIDTH, "height": HEIGHT,
                        "category": "helmet" if index % 2 == 0 else "no_helmet", "box": box, "score": 0.8})
    write_json(root, "materials/proposals.json", records)
    write(root, "materials/previous-run.log", """
        SYNTHETIC LOG from an outdated invocation.
        command: python3 proposal_export.py --input proposals.json --output-format yolo --output labels
        error: unrecognized arguments: --output-format yolo --output labels
    """)
    write(root, "materials/proposal_export.py", '''
        """Synthetic v2 export adapter. Converts saved proposals; performs no inference."""
        import argparse
        import json
        from pathlib import Path
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--input", required=True, type=Path)
        parser.add_argument("--format", required=True, choices=["yolo"])
        parser.add_argument("--output-dir", required=True, type=Path)
        parser.add_argument("--class-map", required=True, type=Path,
                            help="JSON mapping category names to nonnegative integer IDs")
        args = parser.parse_args()
        mapping = json.loads(args.class_map.read_text())
        if any(type(v) is not int or v < 0 for v in mapping.values()):
            parser.error("class IDs must be nonnegative integers")
        items = json.loads(args.input.read_text())
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for item in items:
            x1, y1, x2, y2 = item["box"]
            w, h = item["width"], item["height"]
            cls = mapping[item["category"]]
            line = f"{cls} {(x1+x2)/(2*w):.6f} {(y1+y2)/(2*h):.6f} {(x2-x1)/w:.6f} {(y2-y1)/h:.6f}\\n"
            (args.output_dir / (item["image_id"] + ".txt")).write_text(line)
        print(json.dumps({"synthetic": True, "exported": len(items), "inference_performed": False}))
    ''')
    write(root, "materials/project-notes.md", """
        现有类别顺序：0 = helmet；1 = no_helmet。
        proposals.json 是程序合成的候选框，box 为像素 xyxy，尚无本轮质量验收。
        proposal_export.py 是当前可用的格式导出工具。旧日志保留的是之前的调用方式。
    """)


def annotation_start(root):
    scaffold(root, """
        我想从这批新收集的现场图片开始，准备一个提醒人员不符合戴帽要求的检测模型。
        现在只有少量示例标签，其他相关材料都放在 materials/。请使用辅助训练 Skill，
        检查现状并制定数据标注和后续训练方案，先把这批小样的本地准备工作做起来。
        我希望能直接查看处理结果，再决定是否扩大到更多图片。
        可以查看图片、运行已有本地工具、在 work/ 写脚本和结果；不要覆盖原材料，
        本轮不联网、不安装软件、不调用收费服务、不训练、不部署。
        不清楚的业务问题请主动问我，其他能继续的工作可以先推进。
        这是合成的模拟材料，请按 SYNTHETIC.md 说明实际执行范围。
    """)
    scenes = [
        [{"class": 0, "box": [80, 35, 120, 85], "headwear": "helmet"}],
        [{"class": 1, "box": [80, 35, 120, 85], "headwear": "bare"}],
        [{"class": 0, "box": [45, 35, 85, 85], "headwear": "helmet"}],
        [{"class": 1, "box": [150, 40, 190, 90], "headwear": "bare"}],
        [],
        [{"class": 0, "box": [90, 35, 130, 85], "headwear": "cloth_cap"}],
        [{"class": 0, "box": [40, 35, 80, 85], "headwear": "helmet"},
         {"class": 1, "box": [190, 45, 230, 95], "headwear": "bare"}],
        [{"class": 0, "box": [100, 40, 140, 90], "headwear": "helmet"}],
    ]
    source_groups = ["session_a", "session_b", "session_c", "session_d",
                     "session_e", "session_f", "session_c", "session_g"]
    rows = []
    for index, scene in enumerate(scenes):
        name = f"frame_{index:02d}"
        png(root, f"materials/images/{name}.png", scene, index)
        if index < 2:
            yolo(root, f"materials/example-labels/{name}.txt", scene)
        rows.append({"image_id": name, "image_path": f"images/{name}.png",
                     "width": WIDTH, "height": HEIGHT, "source_group": source_groups[index],
                     "sample_label": f"example-labels/{name}.txt" if index < 2 else "",
                     "split": "unassigned", "synthetic": True})
    write_csv(root, "materials/image-index.csv", rows)
    records = [
        {"proposal_id": "p01", "image_id": "frame_02", "class": 0, "box": [45, 35, 85, 85], "score": 0.91},
        {"proposal_id": "p02", "image_id": "frame_03", "class": 1, "box": [150, 40, 190, 90], "score": 0.87},
        {"proposal_id": "p03", "image_id": "frame_03", "class": 1, "box": [150, 40, 190, 90], "score": 0.63},
        {"proposal_id": "p04", "image_id": "frame_03", "class": 1, "box": [30, 30, 30, 50], "score": 0.82},
        {"proposal_id": "p05", "image_id": "frame_04", "class": 1, "box": [-8, -4, 360, 252], "score": 0.72},
        {"proposal_id": "p06", "image_id": "frame_05", "class": 0, "box": [90, 35, 130, 85], "score": 0.96},
        {"proposal_id": "p07", "image_id": "frame_06", "class": 0, "box": [40, 35, 80, 85], "score": 0.89},
        {"proposal_id": "p08", "image_id": "frame_07", "class": 9, "box": [100, 40, 140, 90], "score": 0.88},
        {"proposal_id": "p09", "image_id": "frame_99", "class": 1, "box": [50, 40, 90, 90], "score": 0.77},
    ]
    write_json(root, "materials/saved-proposals.json", {
        "synthetic": True, "actual_model_inference": False, "coordinate_format": "pixel_xyxy",
        "class_names": {"0": "compliant_headwear", "1": "noncompliant_headwear"},
        "status": "unreviewed_draft", "proposals": records,
    })
    write(root, "materials/README.md", """
        # 新项目留下的材料
        images/ 是 8 张示意图片，image-index.csv 保存了图片尺寸、来源分组和已有示例标签位置。
        example-labels/ 是此前整理的两个小样，格式为 YOLO 归一化框；其业务说明见 label-notes.md。
        saved-proposals.json 是草拟候选框，坐标为像素 xyxy。它没有经过本轮检查，不能直接视为最终标签。
        tools/inspect_saved_proposals.py 可以读取候选文件，打印数量和类别概览；使用 --help 查看参数。
        本批材料没有可用预标注权重，也没有真实模型调用记录。下一批采用什么方法需要结合效果和条件决定。
    """)
    write(root, "materials/label-notes.md", """
        # 已有示例的含义
        类别 0：符合现场戴帽要求；类别 1：不符合现场戴帽要求。框选头部范围。
        frame_00 中的黄色工业安全帽符合要求；frame_01 中裸露头部不符合要求。
        标注的目标是现场规则，不是仅判断头上有没有覆盖物。

        frame_05 的采集备注写着“轻型防撞帽”。现有交接材料没有记录这种帽子在本现场是否允许。
        颜色、候选框类别和置信度都不是现场准入规定；图片本身也不足以读出产品认证。
        这里的帧图、采集备注和候选框均为模拟材料，没有真实现场或厂家证明。
    """)
    write(root, "materials/tools/inspect_saved_proposals.py", '''
        """Inventory saved synthetic proposals. No model is loaded or called."""
        import argparse
        from collections import Counter
        import json
        from pathlib import Path
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--input", required=True, type=Path)
        args = parser.parse_args()
        saved = json.loads(args.input.read_text())
        items = saved["proposals"]
        print(json.dumps({"synthetic": True, "actual_model_inference": False,
                          "proposal_count": len(items),
                          "images_referenced": sorted({item["image_id"] for item in items}),
                          "class_counts": dict(Counter(str(item["class"]) for item in items))}, indent=2))
    ''')


GENERATORS = dict(zip(SCENARIOS, (existing_labels, coverage_gap, metric_regression, resume_rule_change, tool_adaptation, annotation_start)))


def generate(destination, selected):
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination must not exist; choose a new isolated directory")
    destination.mkdir(parents=True)
    for scenario in selected:
        root = destination / scenario
        GENERATORS[scenario](root)
        entries = []
        for file in sorted(root.rglob("*")):
            if file.is_file():
                entries.append({"path": file.relative_to(root).as_posix(), "sha256": hashlib.sha256(file.read_bytes()).hexdigest()})
        write_json(root, "fixture-manifest.json", {"schema": 1, "synthetic": True, "scenario": scenario, "files": entries})
    write_json(destination, "fixture-set.json", {"schema": 1, "synthetic": True, "scenarios": selected})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New isolated directory; existing paths are refused")
    parser.add_argument("--scenario", choices=("all",) + SCENARIOS, default="all")
    args = parser.parse_args()
    selected = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    try:
        generate(args.output, selected)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps({"synthetic": True, "scenarios": selected, "output": str(args.output)}))


if __name__ == "__main__":
    main()
