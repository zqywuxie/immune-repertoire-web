#!/usr/bin/env python3

import argparse
import csv
import gzip
import subprocess
import tempfile
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Read pep CSV/CSV.GZ files, build V/J usage frequency tables, "
            "and generate batch chord diagrams."
        )
    )
    parser.add_argument(
        "input_path",
        help="Path to a pep .csv/.csv.gz file, or a directory containing such files.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        help=(
            "Output directory. Defaults to a sibling directory named "
            "'chord_diagrams' next to the pep directory."
        ),
    )
    parser.add_argument(
        "--count-mode",
        choices=("rows", "copy"),
        default="rows",
        help=(
            "How to count V/J usage. 'rows' counts one row as one observation; "
            "'copy' sums the numeric 'copy' column."
        ),
    )
    parser.add_argument(
        "--skip-plot",
        action="store_true",
        help="Only write the V/J frequency tables and skip PDF chord diagrams.",
    )
    return parser.parse_args()


def iter_input_files(input_path: Path):
    if input_path.is_file():
        return [input_path]
    if input_path.is_dir():
        files = sorted(
            path
            for path in input_path.iterdir()
            if path.is_file() and path.name.endswith((".csv", ".csv.gz"))
        )
        if not files:
            raise FileNotFoundError(f"No .csv or .csv.gz files found in {input_path}")
        return files
    raise FileNotFoundError(f"Input path not found: {input_path}")


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", newline="")
    return path.open("r", newline="")


def strip_table_suffix(name: str):
    for suffix in (".csv.gz", ".csv"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def default_output_dir(input_path: Path):
    if input_path.is_dir():
        return input_path.parent / "chord_diagrams"
    return input_path.parent.parent / "chord_diagrams"


def detect_input_kind(path: Path):
    with open_text(path) as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
    if {"V", "J", "freq"}.issubset(fieldnames):
        return "freq"
    if {"V", "J"}.issubset(fieldnames):
        return "pep"
    raise ValueError(
        f"{path} is missing required columns. Expected pep columns (V,J) or "
        "frequency-table columns (V,J,freq)."
    )


def format_count(count: float, count_mode: str):
    if count_mode == "rows":
        return str(int(count))
    if count.is_integer():
        return str(int(count))
    return f"{count:.6f}"


def build_vj_table_from_pep(path: Path, count_mode: str):
    counts = {}
    total = 0.0

    with open_text(path) as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            v_gene = (row.get("V") or "").strip()
            j_gene = (row.get("J") or "").strip()
            if not v_gene or not j_gene:
                continue

            if count_mode == "copy":
                copy_value = (row.get("copy") or "").strip()
                try:
                    weight = float(copy_value) if copy_value else 0.0
                except ValueError as exc:
                    raise ValueError(
                        f"{path} has a non-numeric copy value: {copy_value!r}"
                    ) from exc
            else:
                weight = 1.0

            if weight <= 0:
                continue

            key = (v_gene, j_gene)
            counts[key] = counts.get(key, 0.0) + weight
            total += weight

    rows = []
    for (v_gene, j_gene), count in sorted(
        counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1])
    ):
        freq = count / total if total else 0.0
        rows.append(
            {
                "V": v_gene,
                "J": j_gene,
                "freq": f"{freq:.10f}",
                "count": format_count(count, count_mode),
            }
        )
    return rows


def load_vj_table(path: Path):
    rows = []
    with open_text(path) as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            v_gene = (row.get("V") or "").strip()
            j_gene = (row.get("J") or "").strip()
            freq_text = (row.get("freq") or "").strip()
            if not v_gene or not j_gene or not freq_text:
                continue
            try:
                freq_value = float(freq_text)
            except ValueError:
                continue
            if freq_value <= 0:
                continue
            record = {
                "V": v_gene,
                "J": j_gene,
                "freq": f"{freq_value:.10f}",
            }
            count_text = (row.get("count") or "").strip()
            if count_text:
                record["count"] = count_text
            rows.append(record)
    return rows


def write_table(rows, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["V", "J", "freq", "count"]
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def get_r_plot_script():
    script_path = Path(__file__).resolve().parent / "20260330" / "make_chord_diagram.r"
    if not script_path.exists():
        raise FileNotFoundError(f"Reference R script not found: {script_path}")
    return script_path


def write_plot_input(rows, output_dir: Path):
    plot_rows = []
    for row in rows:
        v_gene = (row.get("V") or "").strip()
        j_gene = (row.get("J") or "").strip()
        freq_text = (row.get("freq") or "").strip()
        if not v_gene or not j_gene or not freq_text:
            continue
        try:
            freq_value = float(freq_text)
        except ValueError:
            continue
        if freq_value <= 0:
            continue
        plot_rows.append({"V": v_gene, "J": j_gene, "freq": f"{freq_value:.10f}"})

    if not plot_rows:
        raise ValueError("No valid V/J frequency rows available for plotting.")

    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        newline="",
        suffix=".csv",
        prefix="chord_plot_",
        dir=output_dir,
        delete=False,
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=["V", "J", "freq"])
        writer.writeheader()
        writer.writerows(plot_rows)
        return Path(handle.name)


def plot_chord(rows, output_path: Path, title: str):
    del title
    plot_input = write_plot_input(rows, output_path.parent)
    r_script = get_r_plot_script()
    try:
        subprocess.run(
            ["Rscript", str(r_script), str(plot_input), str(output_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Rscript is not available in the current environment.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() or exc.stdout.strip() or "Unknown R plotting error."
        raise RuntimeError(f"R chord plotting failed: {stderr}") from exc
    finally:
        plot_input.unlink(missing_ok=True)


def process_input_file(input_file: Path, args, output_dir: Path):
    input_kind = detect_input_kind(input_file)
    stem = strip_table_suffix(input_file.name)

    if input_kind == "pep":
        rows = build_vj_table_from_pep(input_file, args.count_mode)
        table_path = output_dir / f"{stem}.vj_freq.csv"
        write_table(rows, table_path)
    else:
        rows = load_vj_table(input_file)
        if stem.endswith(".vj_freq"):
            stem = stem[: -len(".vj_freq")]
        table_path = output_dir / f"{stem}.vj_freq.csv"
        write_table(rows, table_path)

    print(f"Wrote table: {table_path}")

    if args.skip_plot:
        return

    pdf_path = output_dir / f"{stem}.pdf"
    plot_chord(rows, pdf_path, title=stem)
    print(f"Wrote plot: {pdf_path}")


def main():
    args = parse_args()
    input_path = Path(args.input_path).expanduser().resolve()
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else default_output_dir(input_path)
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    input_files = iter_input_files(input_path)
    failures = []
    for input_file in input_files:
        print(f"Processing: {input_file}")
        try:
            process_input_file(input_file, args, output_dir)
        except Exception as exc:
            failures.append((input_file, str(exc)))
            print(f"Failed: {input_file}\nReason: {exc}")

    if failures:
        raise SystemExit(
            "\n".join(
                ["One or more files failed:"] + [f"{path}: {msg}" for path, msg in failures]
            )
        )


if __name__ == "__main__":
    main()
