# img_resizer (再帰対応版)

画像のサイズをパーセンテージで変更するPython CLIツールです。

## 特徴
- ファイルまたはフォルダを対象にリサイズ
- フォルダ指定時に `--recursive` オプションで再帰的に処理可能
- サイズは `-p` / `--percent` オプションで指定（デフォルト50%）
- 出力ファイル名に `-o` / `--prefix` オプションでプレフィックスを付与（デフォルト `resized_`）
- 一般的な画像形式に対応（JPEG/PNG/GIF/BMP/TIFF/WebP）
- EXIFの向き補正とメタデータ維持
- アニメGIF対応（フレーム保持）

## 必要なライブラリをインストール

動作にはpillowが必要なので、事前にインストールしてください。

```bash
pip install pillow
````

## 使い方

```bash
# 単一ファイルを30%に縮小
python img_resizer.py filename.png -p 30

# 複数ファイルを75%に拡大、プレフィックスを small_ に変更
python img_resizer.py img1.jpg img2.webp -p 75 -o small_

# フォルダ内の全画像を50%（デフォルト）に縮小
python img_resizer.py ./images

# フォルダ内を再帰的に処理
python img_resizer.py ./images --recursive
```

## オプション一覧

*   `-p`, `--percent` : リサイズ率（%）。例: 30 -> 元の30%に縮小。デフォルト: 50
*   `-o`, `--prefix`  : 出力ファイル名のプレフィックス。デフォルト: resized\_
*   `--recursive`     : フォルダ指定時に再帰的に処理

```

