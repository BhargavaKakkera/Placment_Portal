# Placement Portal

A role-based campus recruitment platform built with FastAPI. The application enables students to apply for jobs, recruiters to manage hiring, and administrators to oversee the placement process through a unified web interface.


## Live Demo

**Application**

https://placement-portal-oftz.onrender.com/

**Swagger UI**

https://placement-portal-oftz.onrender.com/docs


---

## Key Highlights

* Role-based access control (Student, Company, Admin)
* JWT and session-based authentication
* Email verification and password reset
* Job posting and application workflow
* PostgreSQL with Alembic migrations
* Deployed on Render

---

## Features

### Authentication

* Student, Company, and Admin authentication
* Email verification
* Password reset
* Secure password hashing
* JWT authentication for APIs
* Session-based authentication for the web interface

### Student

* Browse available jobs
* Apply for jobs
* Track applications
* View placement offers

### Company

* Register company accounts
* Create and manage job postings
* Review applicants
* Manage offers

### Admin

* Approve company registrations
* Manage users
* Manage jobs and applications
* Monitor placement analytics

### Platform

* Server-rendered UI with JSON APIs
* Request ID tracking
* Security headers
* Rate limiting

---

## Tech Stack

### Backend

* FastAPI
* SQLModel
* SQLAlchemy
* Uvicorn

### Database

* PostgreSQL
* Alembic

### Frontend

* Jinja2 Templates
* HTML
* CSS

### Authentication

* JWT
* Signed Session Cookies
* bcrypt

### Email Service

* SMTP
* Resend

### Deployment

* Render
* Docker

### Other Libraries

* Pydantic
* python-dotenv

---

## Architecture

```text
                Browser
                   │
                   ▼
        FastAPI (UI + REST API)
          │               │
          │               ├── JWT Authentication
          │
          ├── Session Authentication
          │
          ▼
      CRUD / Services
          │
          ▼
 SQLModel / SQLAlchemy
          │
          ▼
 PostgreSQL (Neon)

 Email Service
 (SMTP / Resend)
```

---

## Project Structure

```text
app/
├── crud/             Database operations
├── routers/          API endpoints
├── templates/        HTML templates
├── ui/               Server-rendered pages
├── static/           Static assets
├── auth.py           Authentication and authorization
├── database.py       Database configuration
├── main.py           Application entry point
├── models.py         Database models
└── schemas.py        Request and response schemas

migrations/           Alembic migration files
tests/                Automated tests
requirements.txt      Python dependencies
Dockerfile            Docker configuration
render.yaml           Render deployment
```

## Getting Started

### Clone the Repository

```bash
git clone <repository-url>
cd placement-portal
```

### Create a Virtual Environment

Windows

```bash
python -m venv .venv
.venv\Scripts\activate
```

Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Configure Environment Variables

Create a `.env` file.

### Run Database Migrations

```bash
alembic upgrade head
```

### Start the Application

```bash
uvicorn app.main:app --reload
```

---

## Database

The application uses PostgreSQL for persistent storage.

* Database migrations are managed with Alembic.
* Configure the database using the `DATABASE_URL` environment variable.

Run migrations:

```bash
alembic upgrade head
```

---

## Authentication

* Role-based authentication
* JWT bearer tokens for API endpoints
* Signed session cookies for the web interface
* Email verification
* Password reset
* Secure password hashing

---

## API Documentation

After starting the application:

* Swagger UI: `/docs`
* ReDoc: `/redoc`

---

---

## Deployment

The application is deployed on **Render** with **PostgreSQL (Neon)** as the database backend.

Deployment configuration is provided through `render.yaml`.

---

## Logging

* Structured application logging
* Request ID tracking
* Security and error logging

---

## Error Handling

* Global exception handlers
* Request validation
* Consistent API error responses

---

## Future Improvements

* Redis caching
* Background task processing
* Resume parsing
* Interview scheduling
* Real-time notifications
* Advanced analytics dashboard
