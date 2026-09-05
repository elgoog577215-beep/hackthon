#!/usr/bin/env python3
"""把存量 `mat-*` 资料补登记进教师文件空间（F-3）。

**为什么需要它**：课程生成里的「添加资料」原本只写 `material_storage`，与文件空间
零交集。改造之后新上传会自动登记，但**改造之前传的资料仍然在文件空间里看不到**。
这个脚本把它们补上，保证"旧资料仍在、仍可见"。

**可重跑**：幂等键是 `(owner_id, material_asset_id)`，重复执行不会产生重复条目。
可以先 `--dry-run` 看清单再实际执行。

**归属怎么定**：`MaterialAsset` 没有 owner 字段，课程数据也没有 owner 字段
（核实过：`backend/data/courses/*.json` 里只有块级 `created_by`，不是课程归属）。
所以脚本**不猜归属**：
  - `--owner` 显式指定时，全部登记到该教师名下（单教师部署、或人工确认归属后使用）；
  - 不指定时只做清单输出（dry-run 语义），并说明为什么不能自动判定。
宁可让人来定，也不要把 A 的资料登记到 B 名下——那比看不到更糟。

用法：
    python3 scripts/backfill_material_references.py --dry-run
    python3 scripts/backfill_material_references.py --owner teacher-zhang
    python3 scripts/backfill_material_references.py --owner teacher-zhang --data-dir /path/to/backend
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_repositories(backend_dir: Path):
    sys.path.insert(0, str(backend_dir))
    import material_storage
    import teacher_course_space
    return material_storage, teacher_course_space


def _iter_material_assets(material_storage_module, materials_root: Path):
    """按 asset_id 顺序读出全部存量资产，跳过坏掉的 manifest（不中断整轮）。"""
    for manifest in sorted(materials_root.glob("mat-*/manifest.json")):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            yield material_storage_module.MaterialAsset.model_validate(data)
        except Exception as exc:  # noqa: BLE001 - 坏数据不该让整轮迁移失败
            print(f"  [跳过] {manifest.parent.name}: manifest 无法解析（{exc}）")


def main() -> int:
    parser = argparse.ArgumentParser(description="把存量 mat-* 资料补登记进文件空间")
    parser.add_argument("--owner", default="", help="登记到哪个教师名下（X-User-Id）")
    parser.add_argument("--dry-run", action="store_true", help="只列清单，不写入")
    parser.add_argument(
        "--data-dir", default="",
        help="backend 目录（默认取脚本同级仓库的 backend/）",
    )
    args = parser.parse_args()

    backend_dir = Path(args.data_dir).resolve() if args.data_dir else (
        Path(__file__).resolve().parent.parent / "backend"
    )
    if not (backend_dir / "material_storage.py").is_file():
        print(f"找不到 backend 目录：{backend_dir}")
        return 2

    material_storage, teacher_course_space = _load_repositories(backend_dir)
    materials_root = material_storage.material_repository.root
    repository = teacher_course_space.teacher_course_space_repository

    assets = list(_iter_material_assets(material_storage, materials_root))
    print(f"存量资料：{len(assets)} 份（{materials_root}）")
    if not assets:
        print("没有需要补登记的资料。")
        return 0

    if not args.owner:
        print()
        print("未指定 --owner，仅输出清单（不写入）。")
        print("原因：MaterialAsset 无 owner 字段，课程数据也没有课程级归属，")
        print("      无法自动判定每份资料属于哪位教师。请人工确认后用 --owner 指定。")
        print()
        for asset in assets:
            bound = ",".join(asset.bound_course_ids) or "未绑定课程"
            print(f"  {asset.asset_id}  {asset.filename}  ({bound})")
        return 0

    registered = duplicated = failed = 0
    for asset in assets:
        if args.dry_run:
            print(f"  [dry-run] 将登记 {asset.asset_id} {asset.filename} -> {args.owner}")
            registered += 1
            continue
        try:
            result = repository.register_material_reference(args.owner, asset)
        except Exception as exc:  # noqa: BLE001 - 单份失败不该中断整轮
            failed += 1
            print(f"  [失败] {asset.asset_id} {asset.filename}: {exc}")
            continue
        if result.get("outcome") == "duplicate":
            duplicated += 1
        else:
            registered += 1
            print(f"  [登记] {asset.asset_id} {asset.filename} -> {result['relative_path']}")

    print()
    print(f"完成：新登记 {registered}，已存在 {duplicated}，失败 {failed}")
    if duplicated and not args.dry_run:
        print("（已存在的条目说明脚本重跑过，幂等生效）")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
