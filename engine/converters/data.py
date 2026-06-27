"""
Tabular data / database converter.
Backend: pandas + pyarrow + sqlite3 (stdlib).
Handles: csv, tsv, xlsx, xls, ods, json, parquet, arrow/feather, ndjson/jsonl, sqlite
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


async def convert_data(src: Path, target_ext: str) -> Path:
    """
    Convert tabular data file to target_ext.
    Returns path to converted file.
    """
    try:
        import pandas as pd
    except ImportError:
        raise RuntimeError("pandas não instalado. Execute: pip install pandas openpyxl pyarrow")

    src_ext = src.suffix.lower()
    dest = src.with_suffix(target_ext)

    # ── Read ──────────────────────────────────────────────────────────────────
    df = await _read(pd, src, src_ext)

    # ── Write ─────────────────────────────────────────────────────────────────
    await _write(pd, df, dest, target_ext)
    return dest


async def _read(pd, src: Path, ext: str):
    if ext == ".csv":
        return pd.read_csv(src)
    elif ext == ".tsv":
        return pd.read_csv(src, sep="\t")
    elif ext in (".xlsx", ".xls"):
        return pd.read_excel(src)
    elif ext == ".ods":
        return pd.read_excel(src, engine="odf")
    elif ext == ".json":
        return pd.read_json(src)
    elif ext in (".ndjson", ".jsonl"):
        return pd.read_json(src, lines=True)
    elif ext == ".parquet":
        return pd.read_parquet(src)
    elif ext in (".arrow", ".feather"):
        return pd.read_feather(src)
    elif ext in (".sqlite", ".sqlite3", ".db"):
        return _read_sqlite(pd, src)
    elif ext in (".h5", ".hdf5"):
        return pd.read_hdf(src)
    elif ext == ".avro":
        try:
            import fastavro
            with open(src, "rb") as f:
                records = list(fastavro.reader(f))
            return pd.DataFrame(records)
        except ImportError:
            raise RuntimeError("fastavro não instalado: pip install fastavro")
    elif ext == ".msgpack":
        return pd.read_msgpack(src)
    else:
        raise ValueError(f"Formato de leitura não suportado: {ext}")


async def _write(pd, df, dest: Path, ext: str):
    if ext == ".csv":
        df.to_csv(dest, index=False)
    elif ext == ".tsv":
        df.to_csv(dest, sep="\t", index=False)
    elif ext == ".xlsx":
        df.to_excel(dest, index=False, engine="openpyxl")
    elif ext == ".xls":
        df.to_excel(dest, index=False, engine="xlwt")
    elif ext == ".ods":
        df.to_excel(dest, index=False, engine="odf")
    elif ext == ".json":
        df.to_json(dest, orient="records", indent=2, force_ascii=False)
    elif ext in (".ndjson", ".jsonl"):
        df.to_json(dest, orient="records", lines=True, force_ascii=False)
    elif ext == ".parquet":
        df.to_parquet(dest, index=False)
    elif ext in (".arrow", ".feather"):
        df.to_feather(dest)
    elif ext == ".html":
        df.to_html(dest, index=False)
    elif ext in (".sqlite", ".sqlite3", ".db"):
        import sqlite3 as _sq
        con = _sq.connect(str(dest))
        df.to_sql("data", con, if_exists="replace", index=False)
        con.close()
    else:
        raise ValueError(f"Formato de escrita não suportado: {ext}")


def _read_sqlite(pd, src: Path):
    con = sqlite3.connect(str(src))
    tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", con)
    if tables.empty:
        raise ValueError("SQLite sem tabelas")
    # Read first table
    table_name = tables.iloc[0]["name"]
    df = pd.read_sql(f"SELECT * FROM [{table_name}]", con)
    con.close()
    return df
