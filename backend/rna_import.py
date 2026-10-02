"""Prepare one RNA expression sample for the patient selected at upload."""

import csv
import io
import math
from dataclasses import dataclass

RNA_METADATA_COLUMNS = {"patient_id", "N_unmapped", "N_multimapping", "N_noFeature", "N_ambiguous"}


@dataclass
class PreparedRna:
    content: bytes
    num_genes: int


def prepare_rna_file(
    content: bytes, *, delimiter: str, target_patient_id: str,
    patient_aliases: set[str],
) -> PreparedRna:
    try:
        reader = csv.reader(io.StringIO(content.decode("utf-8-sig")), delimiter=delimiter)
        header = [column.strip() for column in next(reader)]
        rows = [row for row in reader if row and any(value.strip() for value in row)]
    except (UnicodeError, csv.Error, StopIteration) as exc:
        raise ValueError("File RNA rỗng hoặc không đọc được dưới dạng CSV/TSV UTF-8.") from exc

    if not rows:
        raise ValueError("File RNA cần có tiêu đề gene và ít nhất một dòng dữ liệu mẫu.")
    if any(len(row) != len(header) for row in rows):
        raise ValueError("Số giá trị RNA không khớp với số cột trong tiêu đề.")

    patient_column = header.index("patient_id") if "patient_id" in header else None
    matching = [] if patient_column is None else [
        row for row in rows if row[patient_column].strip() in patient_aliases
    ]
    if len(matching) == 1:
        selected = list(matching[0])
    elif len(rows) == 1:
        # A single-sample file can intentionally be assigned to any owned
        # patient. Only the stored copy receives the target patient code.
        selected = list(rows[0])
    else:
        raise ValueError(
            "File RNA chứa nhiều mẫu. Hãy tải file một mẫu hoặc một dòng mẫu "
            "có patient_id trùng với bệnh nhân được chọn."
        )

    gene_columns = [index for index, name in enumerate(header) if name not in RNA_METADATA_COLUMNS]
    if not gene_columns:
        raise ValueError("File RNA không có cột biểu hiện gene.")
    for index in gene_columns:
        value = selected[index].strip()
        try:
            numeric_value = float(value or "0")
        except ValueError as exc:
            raise ValueError(f"Giá trị biểu hiện gene '{header[index]}' phải là số.") from exc
        if not math.isfinite(numeric_value):
            raise ValueError(f"Giá trị biểu hiện gene '{header[index]}' không hợp lệ.")
        if not value:
            selected[index] = "0"

    if patient_column is None:
        header.insert(0, "patient_id")
        selected.insert(0, target_patient_id)
    else:
        selected[patient_column] = target_patient_id

    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=delimiter, lineterminator="\n")
    writer.writerow(header)
    writer.writerow(selected)
    return PreparedRna(output.getvalue().encode("utf-8"), len(gene_columns))
