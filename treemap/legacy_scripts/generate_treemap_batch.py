from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from flask_app.services.treemap_renderer import (
    build_html,
    detect_columns,
    detect_dialect,
    make_title,
    open_text_file,
    read_repertoire,
)


CHAIN_ORDER_TCR = ["TRA", "TRB", "TRD", "TRG"]
CHAIN_ORDER_BCR = ["IGH", "IGK", "IGL"]
CHAIN_ORDER_ALL = CHAIN_ORDER_TCR + CHAIN_ORDER_BCR
FILE_RE = re.compile(r"^(?P<sample>.+?)__(?P<chain>IGH|IGK|IGL|TRA|TRB|TRD|TRG)\.csv\.gz$", re.IGNORECASE)


OVERVIEW_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>__TITLE__</title>
  <style>
    :root{
      --bg:#080808;
      --line:#000000;
      --label-bg:rgba(0,0,0,.72);
      --label-text:#ffffff;
    }
    *{box-sizing:border-box}
    body{
      margin:0;
      background:var(--bg);
      color:#fff;
      font-family:"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
    }
    .page{
      min-height:100vh;
      padding:0;
      background:#000;
    }
    .grid{
      display:grid;
      grid-template-columns:repeat(12, 1fr);
      gap:4px;
      min-height:100vh;
      background:#000;
    }
    .panel{
      position:relative;
      min-height:240px;
      background:#fff;
      overflow:hidden;
      border:1px solid #000;
    }
    .panel iframe{
      width:100%;
      height:100%;
      border:0;
      display:block;
      background:#fff;
    }
    .panel .label{
      position:absolute;
      top:8px;
      left:8px;
      z-index:2;
      padding:4px 8px;
      border-radius:999px;
      background:var(--label-bg);
      color:var(--label-text);
      font-size:12px;
      font-weight:700;
      letter-spacing:.02em;
    }
    .tra,.trb,.trd,.trg{grid-column:span 3; min-height:25vh;}
    .igh,.igk,.igl{grid-column:span 4; min-height:37vh;}
    @media (max-width:1100px){
      .tra,.trb,.trd,.trg,.igh,.igk,.igl{grid-column:span 6; min-height:38vh;}
    }
    @media (max-width:700px){
      .tra,.trb,.trd,.trg,.igh,.igk,.igl{grid-column:1 / -1; min-height:52vh;}
    }
  </style>
</head>
<body>
  <div class="page">
    <div class="grid">
      __PANELS__
    </div>
  </div>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate per-chain treemap HTMLs and a 7-chain overview HTML.")
    parser.add_argument("input_dir", help="Directory containing SAMPLE__CHAIN.csv.gz files")
    parser.add_argument("-o", "--output-dir", default="result_html", help="Directory for generated HTML files")
    parser.add_argument("--min-copy-default", type=int, default=30, help="Default min-copy threshold for each single-chain page")
    parser.add_argument("--top-n", type=int, default=100, help="Top-N rows shown in each single-chain page")
    return parser.parse_args()


def discover_samples(input_dir: Path) -> dict[str, dict[str, Path]]:
    sample_map: dict[str, dict[str, Path]] = {}
    for path in sorted(input_dir.glob("*.csv.gz")):
      match = FILE_RE.match(path.name)
      if not match:
          continue
      sample = match.group("sample")
      chain = match.group("chain").upper()
      sample_map.setdefault(sample, {})[chain] = path
    return sample_map


def detect_columns_for_path(path: Path) -> dict[str, str | None]:
    with open_text_file(path) as handle:
        sample = handle.read(4096)
        handle.seek(0)
        reader = csv.DictReader(handle, dialect=detect_dialect(sample))
        fieldnames = reader.fieldnames or []
    if not fieldnames:
        raise ValueError(f"No header found in {path}")
    overrides = {
        "cdr3": None,
        "copy": None,
        "v": None,
        "j": None,
        "c": None,
        "chain": None,
        "cell_type": None,
    }
    return detect_columns(fieldnames, overrides)


def generate_single_html(input_path: Path, output_path: Path, min_copy_default: int, top_n: int) -> None:
    columns = detect_columns_for_path(input_path)
    clones, summary = read_repertoire(input_path, columns)
    html = build_html(
        clones=clones,
        summary=summary,
        title=make_title(input_path, None),
        source_name=input_path.name,
        columns=columns,
        default_min_copy=min_copy_default,
        top_n=top_n,
    )
    output_path.write_text(html, encoding="utf-8")


def build_overview_html(sample: str, chain_htmls: dict[str, str]) -> str:
    panel_items: list[str] = []
    for chain in CHAIN_ORDER_ALL:
        ref = chain_htmls.get(chain)
        if not ref:
            continue
        panel_items.append(
            f'''<section class="panel {chain.lower()}">
  <div class="label">{chain}</div>
  <iframe src="{ref}?mode=panel" loading="lazy" title="{sample} {chain}"></iframe>
</section>'''
        )
    return OVERVIEW_TEMPLATE.replace("__TITLE__", f"{sample} All Chains Treemap").replace("__PANELS__", "\n".join(panel_items))


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists():
        print(f"Input directory not found: {input_dir}", file=sys.stderr)
        return 1

    sample_map = discover_samples(input_dir)
    if not sample_map:
        print(f"No SAMPLE__CHAIN.csv.gz files found in {input_dir}", file=sys.stderr)
        return 1

    for sample, chain_files in sorted(sample_map.items()):
        chain_htmls: dict[str, str] = {}
        for chain in CHAIN_ORDER_ALL:
            input_path = chain_files.get(chain)
            if not input_path:
                continue
            single_name = f"{sample}__{chain}_treemap.html"
            single_path = output_dir / single_name
            generate_single_html(
                input_path=input_path,
                output_path=single_path,
                min_copy_default=args.min_copy_default,
                top_n=args.top_n,
            )
            chain_htmls[chain] = single_name
            print(f"Single treemap generated: {single_path}")

        overview_path = output_dir / f"{sample}__ALL_treemap.html"
        overview_path.write_text(build_overview_html(sample, chain_htmls), encoding="utf-8")
        print(f"Overview generated: {overview_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
