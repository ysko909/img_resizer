"""
img_resizer.py
画像のサイズをパーセンテージで変更するCLIツール。

- 対象はファイル複数またはフォルダ
- --recursive オプションでサブフォルダも再帰的に処理
- サイズは -p / --percent オプション（デフォルト 50 (%)）で指定
- 出力ファイル名に -o / --prefix オプション（デフォルト 'resized_'）のプレフィックスを付与
- EXIFの向き補正と主要メタデータ（EXIF/ICC）を可能な限り維持
- アニメGIFはフレームごとの持続時間を維持してリサイズ

依存: Pillow (pip install pillow)
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
        help="リサイズ率（%%）。例: 30 -> 元の30%%に縮小。デフォルト: 50"
    )
    parser.add_argument(
        "-o", "--prefix",
        type=str,
        default="resized_",
        help="出力ファイル名のプレフィックス（デフォルト: resized_）"
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="フォルダ指定時、サブフォルダも含めて再帰的に処理する"
    )
    args = parser.parse_args()

    # 入力バリデーション
    if args.percent <= 0:
        parser.error("リサイズ率（-p / --percent）は 0 より大きい値を指定してください。")
    if not args.prefix:
        parser.error("プレフィックス（-o / --prefix）は空文字にできません。")

    return args


def collect_target_files(paths: Iterable[str], recursive: bool = False) -> List[Path]:
    """
    ファイル/フォルダ指定から、処理対象の画像ファイル一覧を収集する。
    """
    targets: List[Path] = []

    for p in paths:
        path = Path(p).resolve()
        if path.is_file():
            if is_supported_image(path):
                targets.append(path)
            else:
                print(f"[SKIP] 非対応または画像ではない可能性: {path.name}", file=sys.stderr)
        elif path.is_dir():
            # 再帰フラグによって探索方法を分岐
            iterator = path.rglob("*") if recursive else path.iterdir()
            
            for child in iterator:
                if child.is_file() and is_supported_image(child):
                    targets.append(child)
        else:
            print(f"[WARN] 見つからないパス: {path}", file=sys.stderr)

    if not targets:
        print("[INFO] 対象となる画像ファイルが見つかりませんでした。", file=sys.stderr)
    
    return targets


def is_supported_image(path: Path) -> bool:
    """
    対応拡張子判定。隠しファイル（.から始まるもの）は除外。
    """
    if path.name.startswith("."):
        return False
        
    if path.suffix.lower() in ALLOWED_EXTS:
        return True
    
    # 拡張子が未知の場合、試しに開いてみる
    try:
        with Image.open(path) as im:
            im.verify()
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
    出力先のユニークなパスを生成。
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
    静止画像のリサイズ。
    ※ 呼び出し側で既に exif_transpose 済みであることを前提とする。
    """
    # パレットモード(P)や1bit(1)の場合、リサイズ品質向上のためRGBA/RGBに変換
    if im.mode in ("P", "1", "LA"):
        im = im.convert("RGBA")

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
    # フォーマット判定
    fmt = (src_info.get("format") or src.suffix.replace(".", "")).upper()
    if fmt == "JPG":
        fmt = "JPEG"

    exif = src_info.get("exif")
    icc = src_info.get("icc_profile")

    save_kwargs = {}
    if icc:
        save_kwargs["icc_profile"] = icc

    # JPEGの場合、アルファチャンネル(RGBA)があると保存できないためRGBに変換
    if fmt == "JPEG":
        if im_resized.mode in ("RGBA", "LA"):
            background = Image.new("RGB", im_resized.size, (255, 255, 255))
            background.paste(im_resized, mask=im_resized.split()[-1])
            im_resized = background
        elif im_resized.mode != "RGB":
            im_resized = im_resized.convert("RGB")
            
        save_kwargs.update({
            "quality": 95,
            "subsampling": 0,
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
        if exif:
            try:
                save_kwargs["exif"] = exif
            except Exception:
                pass

    elif fmt == "WEBP":
        save_kwargs.update({
            "quality": 90,
            "method": 6
        })
        if exif:
            save_kwargs["exif"] = exif

    elif fmt in {"TIFF", "TIF"}:
        if exif:
            save_kwargs["exif"] = exif
        save_kwargs["compression"] = "tiff_lzw"

    # 保存実行
    im_resized.save(dst, format=fmt, **save_kwargs)


def resize_animated_gif(src: Path, percent: float, prefix: str) -> Path:
    """
    アニメGIFをフレームごとにリサイズして保存。
    """
    with Image.open(src) as im:
        loop = im.info.get("loop", 0)
        default_disposal = im.info.get("disposal", 2)
        icc = im.info.get("icc_profile")

        new_size = compute_new_size(im.size, percent)
        
        frames = []
        durations = []
        disposals = []

        for frame in ImageSequence.Iterator(im):
            durations.append(frame.info.get("duration", 100))
            disposals.append(frame.info.get("disposal", default_disposal))

            fr = frame.convert("RGBA").resize(new_size, resample=Image.Resampling.LANCZOS)
            fr = fr.convert("P", palette=Image.Palette.ADAPTIVE, dither=Image.Dither.FLOYDSTEINBERG)
            frames.append(fr)

        if not frames:
            raise ValueError("有効なフレームが見つかりませんでした。")

        dst = unique_output_path(src, prefix)
        
        save_kwargs = {
            "save_all": True,
            "append_images": frames[1:],
            "loop": loop,
            "duration": durations,
            "disposal": disposals,
            "optimize": True,
        }
        if icc:
            save_kwargs["icc_profile"] = icc

        frames[0].save(dst, **save_kwargs)
        return dst


def process_one_image(src: Path, percent: float, prefix: str) -> Optional[Path]:
    """
    1ファイルのリサイズ実行（EXIF回転バグ修正版）。
    """
    try:
        is_animated = False
        src_info = {}
        
        # 1. 予備情報を取得
        with Image.open(src) as im:
            fmt = (im.format or src.suffix.replace(".", "")).upper()
            if fmt == "GIF" and getattr(im, "n_frames", 1) > 1:
                is_animated = True
            
            src_info = {
                "format": fmt,
                "exif": im.info.get("exif"),
                "icc_profile": im.info.get("icc_profile"),
            }

        # 2. アニメーションGIFの場合
        if is_animated:
            return resize_animated_gif(src, percent, prefix)
        
        # 3. 静止画の場合
        with Image.open(src) as im:
            # --- 修正ポイント：リサイズ計算の前に回転を適用する ---
            im = ImageOps.exif_transpose(im)
            
            # 正しい向きになった後の im.size を使って計算
            new_size = compute_new_size(im.size, percent)
            
            # リサイズ実行
            im_resized = resize_static_image(im, new_size)
            
            # 保存
            dst = unique_output_path(src, prefix)
            save_image_with_metadata(im_resized, src, dst, src_info)
            return dst

    except Exception as e:
        print(f"[ERROR] 変換失敗: {src.name} -> {e}", file=sys.stderr)
        return None


def main() -> None:
    args = parse_args()
    
    # ターゲット収集
    targets = collect_target_files(args.paths, recursive=args.recursive)

    if not targets:
        sys.exit(1)

    percent = args.percent
    prefix = args.prefix

    print(f"--- 開始 ---")
    print(f"対象数: {len(targets)} ファイル")
    print(f"設定: {percent}% リサイズ / プレフィックス: '{prefix}'")
    if args.recursive:
        print("モード: 再帰処理 ON")
    print("-----------------------------------")

    success_count = 0
    for i, src in enumerate(targets, 1):
        dst = process_one_image(src, percent, prefix)
        if dst:
            success_count += 1
            print(f"[{i}/{len(targets)}] OK: {src.name} -> {dst.name}")
        else:
            print(f"[{i}/{len(targets)}] NG: {src.name}")

    print("-----------------------------------")
    print(f"[完了] 成功: {success_count} / 失敗: {len(targets) - success_count}")
    
    if success_count < len(targets):
        sys.exit(2)


if __name__ == "__main__":
    main()