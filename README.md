# Manufacturing Network Platform - Backend

Backend API for a B2B platform connecting manufacturing companies. The platform acts as the middleman: any company can be a buyer in one order and a seller in another.

## Tech Stack

- **Python** 3.12+
- **Django** + **Django REST Framework**
- **PostgreSQL**
- **django-environ** for configuration
- Planned: Celery + Redis, JWT auth, drf-spectacular (OpenAPI), FastAPI AI service (later)

## Project Structure

```
manufacturing-network-backend/
├── config/            # Project settings, URLs, ASGI/WSGI
├── manage.py          # Django command-line tool
├── requirements.txt   # Python dependencies
├── .env               # Local secrets (not committed)
└── .gitignore
```

Apps (to be added): `users`, `organizations`, and later `catalog`, `rfq`, `orders`, `billing`.

## Getting Started

### 1. Clone the repository

```
git clone https://github.com/SatyasriMallula/manufacturing-network-backend.git
cd manufacturing-network-backend
```

### 2. Create and activate a virtual environment

Windows (PowerShell):

```
python -m venv venv
venv\Scripts\activate
```

Mac/Linux:

```
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```
python -m pip install -r requirements.txt
```

### 4. Create the database

In pgAdmin or `psql`:

```
CREATE DATABASE b2b_db;
```

### 5. Configure environment variables

Create a `.env` file next to `manage.py`:

```
SECRET_KEY=change-this-to-a-long-random-string
DEBUG=True
DB_NAME=b2b_db
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=localhost
DB_PORT=5432
```

Never commit `.env` to Git.

### 6. Run migrations and start the server

```
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000 (API) and http://127.0.0.1:8000/admin (admin panel).

## Useful Commands

| Command | Purpose |
|---|---|
| `python manage.py startapp <name>` | Create a new app |
| `python manage.py makemigrations` | Generate migrations from model changes |
| `python manage.py migrate` | Apply migrations |
| `python manage.py test` | Run tests |
| `python -m pip freeze > requirements.txt` | Update dependency list |

If `django-admin.exe` or `pip.exe` is blocked by a Windows policy, use `python -m django ...` and `python -m pip ...` instead.

## Roadmap

- [x] Project setup
- [ ] Custom User model (`AUTH_USER_MODEL`)
- [ ] Organization and Membership models (users belong to companies, with roles)
- [ ] Roles and permissions (8 roles)
- [ ] JWT authentication
- [ ] Catalog, RFQ, Quote, Order, Invoice, Payment models
- [ ] Data isolation so companies only see their own data
- [ ] REST API with OpenAPI docs
- [ ] Celery + Redis for background jobs
- [ ] Dockerize and deploy
- [ ] AI service (FastAPI), after the core product works

## Design Notes

- Buyer and seller are roles in an order (`buyer_org`, `seller_org`), not types of companies.
- Users belong to organizations through a membership table, so one person can hold several roles.
- Modular monolith first; split out services only when there is a clear need.

## License

Private project. All rights reserved.
