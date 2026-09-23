import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def sample_data(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    pd.DataFrame(
        [
            (1, 0, True),
            (2, 1, False),
            (3, 2, False),
            (4, 4, False),
            (5, 0, True),
            (6, 3, False),
        ],
        columns=["gid", "depth", "is_seed"],
    ).to_parquet(data / "nodes.parquet", index=False)
    pd.DataFrame(
        [(1, 2, 10000, 1, 1), (2, 3, 9000, 1, 2), (3, 4, 8000, 1, 4), (2, 6, 1000, 1, 3)],
        columns=["src", "dst", "sum_kzt", "n_tx", "depth"],
    ).to_parquet(data / "edges.parquet", index=False)
    pd.DataFrame(
        [
            (1, 2, "2026-07-01", 10000),
            (2, 3, "2026-07-02", 9000),
            (3, 4, "2026-07-03", 8000),
            (2, 6, "2026-07-04", 1000),
        ],
        columns=["src", "dst", "date", "sum_kzt"],
    ).to_parquet(data / "transactions.parquet", index=False)
    return data
