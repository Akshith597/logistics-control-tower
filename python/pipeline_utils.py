"""Small reliability helpers shared by the Python pipeline scripts."""

from contextlib import contextmanager
import hashlib
from pathlib import Path


def require_file(path, label="Required file"):
    """Return *path* or fail before a library creates an empty replacement."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found:\n{path}")
    return path


def require_named_files(folder, names, suffix=""):
    """Validate a complete input contract and return paths in contract order."""
    folder = Path(folder)
    paths = tuple(folder / f"{name}{suffix}" for name in names)
    missing = tuple(path for path in paths if not path.is_file())

    if missing:
        missing_list = "\n".join(f"  - {path}" for path in missing)
        raise FileNotFoundError(
            "Pipeline input contract is incomplete. Missing files:\n"
            f"{missing_list}"
        )

    return paths


def file_sha256(file_path):
    """Return a stable source fingerprint for data-lineage checks."""
    digest = hashlib.sha256()
    with Path(file_path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@contextmanager
def duckdb_transaction(database_file, *, must_exist=True):
    """Yield a DuckDB connection and commit or roll back the complete step."""
    import duckdb

    database_file = Path(database_file)

    if must_exist:
        require_file(database_file, "Database")
    else:
        database_file.parent.mkdir(parents=True, exist_ok=True)

    connection = duckdb.connect(str(database_file))
    transaction_started = False

    try:
        connection.execute("BEGIN TRANSACTION")
        transaction_started = True
        yield connection
        connection.execute("COMMIT")
        transaction_started = False
    except BaseException:
        if transaction_started:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def atomic_csv(dataframe, output_file, *, columns=None):
    """Write a CSV with a stable schema and replace the prior file on success."""
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = output_file.with_name(f".{output_file.name}.tmp")

    if columns is not None:
        dataframe = dataframe.reindex(columns=columns)

    try:
        dataframe.to_csv(
            temporary_file,
            index=False,
            lineterminator="\n",
        )
        temporary_file.replace(output_file)
    finally:
        temporary_file.unlink(missing_ok=True)
