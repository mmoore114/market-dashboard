"""Exact full-population Parquet readback with bounded comparison buffers."""

import pandas as pd
import pyarrow.parquet as pq


def verify_frame(path, frame, *, batch_size=4096):
    parquet = pq.ParquetFile(path)
    if parquet.schema_arrow.names != list(frame.columns):
        raise ValueError("INPUT_READBACK_COLUMNS_MISMATCH")
    offset = 0
    for batch in parquet.iter_batches(batch_size=batch_size):
        actual = batch.to_pandas().astype(object)
        expected = (
            frame.iloc[offset : offset + len(actual)]
            .reset_index(drop=True)
            .astype(object)
        )
        pd.testing.assert_frame_equal(
            actual.where(pd.notna(actual), None),
            expected.where(pd.notna(expected), None),
            check_dtype=False,
            check_exact=True,
        )
        offset += len(actual)
    if offset != len(frame):
        raise ValueError("INPUT_READBACK_ROW_COUNT_MISMATCH")
