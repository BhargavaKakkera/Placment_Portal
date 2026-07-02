from sqlalchemy import inspect

from app.database import engine


inspector = inspect(engine)
tables = inspector.get_table_names()

print("\nDatabase schema")

for table_name in sorted(tables):
    print(f"\nTable: {table_name}")

    columns = inspector.get_columns(table_name)
    print("\n  Columns:")
    for col in columns:
        nullable = "NULL" if col["nullable"] else "NOT NULL"
        col_type = str(col["type"])
        default = f" [DEFAULT: {col.get('default')}]" if col.get("default") else ""
        print(f'    - {col["name"]:<30} {col_type:<25} {nullable:<10}{default}')

    pk = inspector.get_pk_constraint(table_name)
    if pk and pk["constrained_columns"]:
        print(f'\n  Primary key: {pk["constrained_columns"]}')

    fks = inspector.get_foreign_keys(table_name)
    if fks:
        print("\n  Foreign keys:")
        for fk in fks:
            local_cols = ", ".join(fk["constrained_columns"])
            remote_table = fk["referred_table"]
            remote_cols = ", ".join(fk["referred_columns"])
            ondelete = fk.get("ondelete", "NO ACTION")
            print(f"    - {local_cols:<40} -> {remote_table}({remote_cols})")
            print(f"      ON DELETE: {ondelete}")

    indexes = inspector.get_indexes(table_name)
    if indexes:
        print("\n  Indexes:")
        for idx in indexes:
            cols = ", ".join(idx["column_names"])
            unique = "UNIQUE" if idx["unique"] else "NON-UNIQUE"
            print(f'    - {idx["name"]:<40} ({cols}) [{unique}]')

print("\nEnd of schema\n")
