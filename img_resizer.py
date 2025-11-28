"""
img_resizer.py
画像のサイズをパーセンテージで変更するCLIツール。

- 対象はファイル複数またはフォルダ（フォルダ直下の画像ファイルが対象）
- サイズは -p / --percent オプション（デフォルト 50 (%)）で指定
- 出力ファイル名に -o / --prefix オプション（デフォルト 'resized_'）のプレフィックスを付与
- 一般的な画像形式に対応（JPEG/PNG/GIF/BMP/TIFF/WebP 等）
- EXIFの向き補正と主要メタデータ（EXIF/ICC）を可能な限り維持
- アニメGIFはフレームを維持してリサイズ

依存: Pillow (pip install pillow)
Python: 3.13.0 で動作確認想定
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List, Tuple, Optional

from PIL import Image, ImageOps, ImageSequence

# 対応拡張子（小文字）
ALLOWED_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp"
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="img_resizer",
        description="画像ファイルをパーセンテージ指定でリサイズします。"
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="対象のファイルまたはフォルダ（複数指定可）。絶対パス/相対パスいずれも可。"
    )
    parser.add_argument(
        "-p", "--percent",
        type=float,
        default=50.0,
        help="リサイズ率（%）。例: 30 -> 元の30%%に縮小。デフォルト: 50"
    )
    parser.add_argument(
        "-o", "--prefix",
        type=str,
        default="resized_",
        help="出力ファイル名のプレフィックス（デフォルト: resized_）"
    )
    args = parser.parse_args()

    # 入力バリデーション
    if args.percent <= 0:
        parser.error("リサイズ率（-p / --percent）は 0 より大きい値を指定してください。")
    if not args.prefix:
        parser.error("プレフィックス（-o / --prefix）は空文字にできません。")

    return args


def collect_target_files(paths: Iterable[str]) -> List[Path]:
    """
    ファイル/フォルダ指定から、処理対象の画像ファイル一覧を収集する。
    フォルダ指定の場合は直下のファイルのみを対象（再帰なし）。
    """
    targets: List[Path] = []

    for p in paths:
        path = Path(p).resolve()
        if path.is_file():
            # ファイルは拡張子チェックで一般的な画像のみ対象
            if is_supported_image(path):
                targets.append(path)
            else:
                print(f"[SKIP] 非対応または画像ではない可能性: {path}", file=sys.stderr)
        elif path.is_dir():
            for child in path.iterdir():
                if child.is_file() and is_supported_image(child):
                    targets.append(child)
        else:
            print(f"[WARN] 見つからないパス（ファイル/フォルダではない）: {path}", file=sys.stderr)

    if not targets:
        print("[INFO] 対象となる画像ファイルが見つかりませんでした。", file=sys.stderr)
    return targets


def is_supported_image(path: Path) -> bool:
    """
    対応拡張子判定。拡張子が不明でも画像の可能性がある場合は、Pillowでのオープン可否で最終判断。
    """
    if path.suffix.lower() in ALLOWED_EXTS:
        return True
    # 拡張子が未知の場合、試しに開いてみる
    try:
        with Image.open(path) as im:
            im.verify()  # ヘッダ検証
        return True
    except Exception:
        return False


def compute_new_size(orig_size: Tuple[int, int], percent: float) -> Tuple[int, int]:
    w, h = orig_size
    scale = percent / 100.0
    new_w = max(1, round(w * scale))
    new_h = max(1, round(h * scale))
    return new_w, new_h


def unique_output_path(src: Path, prefix: str) -> Path:
    """
    出力先のユニークなパスを生成。基本は <prefix><元ファイル名> とし、
    既存の場合は連番を付与（例: resized_sample.png, resized_sample_1.png, ...）。
    """
    base_name = f"{prefix}{src.stem}"
    out = src.with_name(f"{base_name}{src.suffix}")
    idx = 1
    while out.exists():
        out = src.with_name(f"{base_name}_{idx}{src.suffix}")
        idx += 1
    return out


def resize_static_image(
    im: Image.Image,
    new_size: Tuple[int, int]
) -> Image.Image:
    """
    静止画像のリサイズ（EXIFの向き補正込み）。
    """
    # EXIFの向き補正
    im = ImageOps.exif_transpose(im)

    # 高品質リサンプル
    return im.resize(new_size, resample=Image.Resampling.LANCZOS)


def save_image_with_metadata(
    im_resized: Image.Image,
    src: Path,
    dst: Path,
    src_info: dict
) -> None:
    """
    形式ごとのメタデータ配慮をしつつ保存。
    """
    fmt = (src_info.get("format") or src.suffix.replace(".", "")).upper()
    exif = src_info.get("exif")
    icc = src_info.get("icc_profile")

    save_kwargs = {}
    if icc:
        save_kwargs["icc_profile"] = icc

    # 形式別のおすすめパラメータ
    if fmt in {"JPG", "JPEG"}:
        save_kwargs.update({
            "quality": 95,
            "subsampling": "keep",
            "progressive": True,
            "optimize": True
        })
        if exif:
            save_kwargs["exif"] = exif
    elif fmt == "PNG":
        save_kwargs.update({
            "optimize": True,
            "compress_level": 9
        })
    elif fmt == "WEBP":
        save_kwargs.update({
            "quality": 90,
            "method": 6
        })
    elif fmt in {"TIFF", "TIF"}:
        # TIFFのEXIFを維持
        if exif:
            save_kwargs["exif"] = exif

    # 保存
    im_resized.save(dst, **save_kwargs)


def resize_animated_gif(src: Path, percent: float, prefix: str) -> Path:
    """
    アニメGIFをフレームごとにリサイズして、アニメーションを維持したまま保存。
    """
    with Image.open(src) as im:
        # GIF固有情報
        loop = im.info.get("loop", 0)
        duration = im.info.get("duration", 100)  # ms
        disposal = im.info.get("disposal", 2)
        transparency = im.info.get("transparency")
        icc = im.info.get("icc_profile")

        new_size = compute_new_size(im.size, percent)
        frames = []

        for frame in ImageSequence.Iterator(im):
            # 各フレームもEXIF向き補正（GIFには通常EXIFはないが念のため）
            fr = ImageOps.exif_transpose(frame)
            fr = fr.convert("RGBA").resize(new_size, resample=Image.Resampling.LANCZOS)
            # GIF保存に適したパレットへ変換
            fr = fr.convert("P", palette=Image.Palette.ADAPTIVE)
            frames.append(fr)

        dst = unique_output_path(src, prefix)
        first = frames[0]
        save_kwargs = {
            "save_all": True,
            "append_images": frames[1:],
            "loop": loop,
            "duration": duration,
            "disposal": disposal,
            "optimize": True,
        }
        if transparency is not None:
            save_kwargs["transparency"] = transparency
        if icc:
            save_kwargs["icc_profile"] = icc

        first.save(dst, **save_kwargs)
        return dst


def process_one_image(src: Path, percent: float, prefix: str) -> Optional[Path]:
    """
    1ファイルのリサイズ実行。成功時は出力パス、失敗時は None を返す。
    """
    try:
        with Image.open(src) as im:
            fmt = (im.format or src.suffix.replace(".", "")).upper()
            # アニメGIF対応
            if fmt == "GIF" and getattr(im, "n_frames", 1) > 1:
                return resize_animated_gif(src, percent, prefix)

            src_info = {
                "format": fmt,
                "exif": im.info.get("exif"),
                "icc_profile": im.info.get("icc_profile"),
            }

            new_size = compute_new_size(im.size, percent)
            im_resized = resize_static_image(im, new_size)
            dst = unique_output_path(src, prefix)
            save_image_with_metadata(im_resized, src, dst, src_info)
            return dst
    except Exception as e:
        print(f"[ERROR] 変換失敗: {src} -> {e}", file=sys.stderr)
        return None


def main() -> None:
    args = parse_args()
    targets = collect_target_files(args.paths)

    if not targets:
        sys.exit(1)

    percent = args.percent
    prefix = args.prefix

    print(f"[INFO] 対象ファイル数: {len(targets)} / リサイズ率: {percent:.2f}% / 出力プレフィックス: '{prefix}'")
    success = 0
    for src in targets:
        dst = process_one_image(src, percent, prefix)
        if dst:
            success += 1
            print(f"[OK] {src.name} -> {dst.name}")
        else:
            print(f"[FAIL] {src.name}", file=sys.stderr)

    print(f"[DONE] 成功: {success} / 失敗: {len(targets) - success}")
    # エラーがあれば非ゼロ終了コード
    if success < len(targets):
        sys.exit(2)


if __name__ == "__main__":
    main()
