## Environment

Required local values in [.env](/d:/pp/.env):

```env
SECRET_KEY=...
ACCESS_TOKEN_EXPIRE_MINUTES=60
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES=15
DEBUG=True
DB_CONNECT_TIMEOUT_SECONDS=5
DATABASE_URL=postgresql+psycopg://postgres:2005@localhost:5432/placment_portal
TEST_DATABASE_URL=postgresql+psycopg://postgres:2005@localhost:5432/test_placment_portal
```

App database:
- `placment_portal`

Test database:
- `test_placment_portal`
