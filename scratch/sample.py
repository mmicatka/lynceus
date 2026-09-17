import pyarrow as pa
import pyarrow.parquet as pq

input_file = "parquet/sample.parquet"
output_file = "parquet/sample_50k.parquet"
target_rows = 50_000

parquet_file = pq.ParquetFile(input_file)
selected_batches = []
rows_accumulated = 0

for batch in parquet_file.iter_batches():
    needed = target_rows - rows_accumulated

    if batch.num_rows <= needed:
        selected_batches.append(batch)
        rows_accumulated += batch.num_rows
    else:
        selected_batches.append(batch.slice(0, needed))
        rows_accumulated += needed

    if rows_accumulated >= target_rows:
        break

table = pa.Table.from_batches(selected_batches)
pq.write_table(table, output_file)
