# it is just for development purpose only.
"""Display complete database schema."""

from sqlalchemy import inspect
from app.database import engine

inspector = inspect(engine)
tables = inspector.get_table_names()

print('\n' + '='*100)
print('DATABASE SCHEMA - All Tables, Columns, and Foreign Key References')
print('='*100)

for table_name in sorted(tables):
    print(f'\n📋 TABLE: {table_name.upper()}')
    print('─' * 100)
    
    # Get columns
    columns = inspector.get_columns(table_name)
    print('\n  COLUMNS:')
    for col in columns:
        nullable = 'NULL' if col['nullable'] else 'NOT NULL'
        col_type = str(col['type'])
        default = f" [DEFAULT: {col.get('default')}]" if col.get('default') else ""
        print(f'    • {col["name"]:<30} {col_type:<25} {nullable:<10}{default}')
    
    # Get primary keys
    pk = inspector.get_pk_constraint(table_name)
    if pk and pk['constrained_columns']:
        print(f'\n  PRIMARY KEY: {pk["constrained_columns"]}')
    
    # Get foreign keys
    fks = inspector.get_foreign_keys(table_name)
    if fks:
        print('\n  FOREIGN KEYS:')
        for fk in fks:
            local_cols = ', '.join(fk['constrained_columns'])
            remote_table = fk['referred_table']
            remote_cols = ', '.join(fk['referred_columns'])
            ondelete = fk.get('ondelete', 'NO ACTION')
            print(f'    • {local_cols:<40} → {remote_table}({remote_cols})')
            print(f'      ON DELETE: {ondelete}')
    
    # Get indexes
    indexes = inspector.get_indexes(table_name)
    if indexes:
        print('\n  INDEXES:')
        for idx in indexes:
            cols = ', '.join(idx['column_names'])
            unique = 'UNIQUE' if idx['unique'] else 'NON-UNIQUE'
            print(f'    • {idx["name"]:<40} ({cols}) [{unique}]')

print('\n' + '='*100)
print('END OF SCHEMA')
print('='*100 + '\n')
