> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

This guide explains what each folder in the repository does and where you should look when working on a task.

Repository:

```text
lorrysystem-marketing-system/
```

The main parts of the system are:

```text
API
Dashboard
Database Migrations
Docker
n8n
```

The basic architecture is:

```text
Dashboard
    ↓
Marketing API
    ↓
PostgreSQL

n8n
    ↓
Marketing API
    ↓
PostgreSQL
```

The Dashboard and n8n should **never connect directly to PostgreSQL**.

---

# 1. Root Directory

The root of the repository looks roughly like this:

```text
lorrysystem-marketing-system/
│
├── api/
├── dashboard/
├── database/
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

Each part has a different purpose.

---

# 2. `api/`

```text
api/
```

This is the main backend of the system.

It is written using:

```text
Python
FastAPI
SQLAlchemy
```

Most backend development will happen here.

Structure:

```text
api/
├── app/
├── scripts/
├── alembic/
├── Dockerfile
├── requirements.txt
└── alembic.ini
```

---

# 3. `api/app/`

```text
api/app/
```

This contains the main FastAPI application.

Structure:

```text
app/
├── core/
├── db/
├── models/
├── routers/
├── schemas/
├── services/
├── main.py
└── security.py
```

---

# 4. `api/app/main.py`

```text
api/app/main.py
```

This is where the FastAPI application starts.

It loads and registers the API routers.

You normally do not need to make major changes here unless:

- adding a completely new router
    
- changing application startup behavior
    
- changing middleware
    
- changing application-wide settings
    

---

# 5. `api/app/security.py`

```text
api/app/security.py
```

This handles API authentication.

Protected API routes require:

```text
X-API-Key
```

Do not hard-code API keys here.

API keys must come from environment variables.

---

# 6. `api/app/core/`

```text
api/app/core/
```

This contains application-wide configuration.

For example:

```text
config.py
```

This usually handles things such as:

- environment variables
    
- API configuration
    
- database configuration
    
- application settings
    

If a task involves configuration, check this folder first.

---

# 7. `api/app/db/`

```text
api/app/db/
```

This contains database connection logic.

Examples:

```text
base.py
session.py
```

This folder handles how FastAPI connects to PostgreSQL using SQLAlchemy.

You should normally not put business logic here.

---

# 8. `api/app/models/`

```text
api/app/models/
```

This contains the SQLAlchemy database models.

Models describe how tables look inside PostgreSQL.

Current areas include:

```text
catalog.py
companies.py
discovery.py
leads.py
marketing.py
```

Examples of things represented here:

- Companies
    
- Contacts
    
- Leads
    
- Lead Candidates
    
- Research
    
- Scores
    
- Product Matches
    
- Marketing Actions
    
- Approval Requests
    

If you need to change the database structure, you may need to change a model here.

Important:

Changing a model does **not automatically change the database**.

A database migration must also be created.

---

# 9. `api/app/schemas/`

```text
api/app/schemas/
```

Schemas define the data that goes into and comes out of the API.

The project uses Pydantic schemas.

Examples:

```text
candidate.py
company.py
contact.py
lead.py
research.py
scoring.py
product_matching.py
marketing_action.py
approval.py
```

Think of schemas as:

```text
"What data does this API endpoint accept?"

and

"What data does this API endpoint return?"
```

Example:

```text
POST /api/companies
```

may receive a CompanyCreate schema and return a CompanyResponse schema.

If an API request or response needs a new field, this folder will probably need changes.

---

# 10. `api/app/routers/`

```text
api/app/routers/
```

This is where the API endpoints are defined.

Current routers include:

```text
approvals.py
candidates.py
companies.py
contacts.py
health.py
leads.py
marketing_actions.py
product_matching.py
public_fetch.py
research.py
scoring.py
```

The project currently has:

```text
53 API endpoints
```

Split into:

```text
27 GET
15 POST
11 PATCH
```

If you want to know:

```text
"What URL does this feature use?"
```

or

```text
"Where is this endpoint created?"
```

look inside `routers/`.

For example:

```text
api/app/routers/research.py
```

contains Research API endpoints.

---

# 11. `api/app/services/`

```text
api/app/services/
```

This is where the main business logic should live.

Current services include:

```text
approval_service.py
candidate_service.py
company_service.py
contact_service.py
lead_service.py
marketing_action_service.py
product_matching_service.py
public_fetch_guard.py
research_service.py
scoring_service.py
```

The easiest way to understand the difference is:

```text
Router
    ↓
receives HTTP request

Service
    ↓
does the actual work

Model
    ↓
reads/writes database
```

Example:

```text
POST /api/research/...
```

would normally be:

```text
research.py router
        ↓
research_service.py
        ↓
database models
```

Try to keep complicated logic inside services rather than putting everything inside the router.

---

# 12. `api/scripts/`

```text
api/scripts/
```

This contains test and validation scripts.

Examples:

```text
test_full_api.py
validate_candidate_api.py
validate_research_api.py
validate_scoring_api.py
validate_product_matching_api.py
validate_marketing_actions_api.py
validate_approval_api.py
validate_full_stack.py
```

These are very useful when testing changes.

Before saying that a task is finished, run the relevant validation script where possible.

For example, if you change Research:

```text
validate_research_api.py
```

should be checked.

---

# 13. `api/requirements.txt`

```text
api/requirements.txt
```

This lists the Python packages required by the API.

If you add a new Python library, it may need to be added here.

Do not install random libraries without discussing it first.

---

# 14. `api/Dockerfile`

```text
api/Dockerfile
```

This tells Docker how to build the Marketing API container.

You normally do not need to change this unless the application requires:

- new system packages
    
- different Python configuration
    
- a different build process
    

---

# 15. `database/`

```text
database/
```

This contains database migration files.

Structure:

```text
database/
└── migrations/
    └── versions/
```

Current migration history reaches:

```text
008
```

The chain is:

```text
001
 ↓
002
 ↓
003
 ↓
d62d40479f83
 ↓
005
 ↓
006
 ↓
007
 ↓
008
```

A migration describes how the database structure changes.

For example:

```text
add a column
create a table
create an index
change a constraint
```

Important rule:

Do not edit old migrations that have already been applied.

Create a new migration instead.

---

# 16. `dashboard/`

```text
dashboard/
```

This contains the web interface.

It uses:

```text
FastAPI
Jinja2
HTML
CSS
HTTPX
```

The Dashboard does not access PostgreSQL directly.

It calls the Marketing API.

Structure:

```text
dashboard/
├── app/
├── scripts/
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

# 17. `dashboard/app/main.py`

```text
dashboard/app/main.py
```

This contains the Dashboard routes.

Examples may include pages such as:

```text
/dashboard
/leads
/approvals
/actions
```

If you need to add a new page, this file may need changes.

---

# 18. `dashboard/app/api_client.py`

```text
dashboard/app/api_client.py
```

This handles communication between the Dashboard and Marketing API.

Think of it as:

```text
Dashboard
   ↓
api_client.py
   ↓
Marketing API
```

If the Dashboard needs to call a new API endpoint, this is one of the first places to check.

---

# 19. `dashboard/app/config.py`

```text
dashboard/app/config.py
```

This loads Dashboard configuration such as:

- Marketing API URL
    
- API key
    
- session secret
    
- reviewer identity
    
- ICP IDs
    

Never hard-code real secrets into this file.

---

# 20. `dashboard/app/templates/`

```text
dashboard/app/templates/
```

This contains the HTML pages.

Current templates include things such as:

```text
dashboard.html
leads.html
lead_detail.html
lead_new.html
lead_manual.html
lead_import.html
discovered_leads.html
discovered_lead_detail.html
approvals.html
approval_detail.html
actions.html
system.html
```

If your task is mostly changing:

```text
page layout
text
buttons
forms
tables
HTML structure
```

you will probably work here.

---

# 21. `dashboard/app/static/`

```text
dashboard/app/static/
```

This contains static frontend files.

Currently this includes:

```text
app.css
```

If your task involves:

```text
colours
spacing
layout
fonts
button styling
table styling
```

look here.

---

# 22. `dashboard/scripts/`

```text
dashboard/scripts/
```

Contains Dashboard validation scripts.

For example:

```text
validate_lead_imports.py
```

Use these where relevant after modifying Dashboard functionality.

---

# 23. `docker-compose.yml`

```text
docker-compose.yml
```

This defines the DEV application containers.

It includes things such as:

```text
PostgreSQL
Marketing API
Dashboard
Docker networks
Volumes
Environment variables
Ports
```

Be careful when changing this file.

A mistake here can stop the entire DEV application from starting.

Do not add DEV containers to PROD networks.

---

# 24. `.env.example`

```text
.env.example
```

This is an example environment configuration.

It shows which environment variables are required.

It does **not** contain real passwords or API keys.

Example:

```text
POSTGRES_PASSWORD=CHANGE_ME
MARKETING_API_KEY=CHANGE_ME
```

Your real `.env` file stays on your computer/server and must never be committed.

---

# 25. `.gitignore`

```text
.gitignore
```

This tells Git which files must not be uploaded.

Examples include:

```text
.env
data/
secrets/
.n8n/
database runtime files
private keys
backups
logs
```

Do not remove security-related entries from `.gitignore` without discussing it first.

---

# 26. `README.md`

```text
README.md
```

This contains the main project documentation.

Read this before starting development.

It explains:

- project architecture
    
- DEV and PROD
    
- API count
    
- Git workflow
    
- deployment workflow
    
- security rules
    

---

# 27. n8n

n8n is part of the system but currently lives outside this Git repository.

DEV n8n:

```text
/opt/lorrysystem/dev/n8n-dev
```

PROD n8n:

```text
/opt/lorrysystem/prod/n8n
```

n8n handles automation and workflow orchestration.

Examples:

```text
Research automation
Lead processing
API workflows
Background automation
```

Do not modify n8n workflows unless specifically instructed.

---

# 28. How to Find the Right File

If the task says:

### "Add or change an API endpoint"

Look at:

```text
api/app/routers/
api/app/schemas/
api/app/services/
```

### "Change business logic"

Look at:

```text
api/app/services/
```

### "Change database structure"

Look at:

```text
api/app/models/
database/migrations/
```

### "Change what the API accepts or returns"

Look at:

```text
api/app/schemas/
```

### "Change a Dashboard page"

Look at:

```text
dashboard/app/templates/
dashboard/app/main.py
```

### "Change Dashboard styling"

Look at:

```text
dashboard/app/static/app.css
```

### "Make Dashboard call a new API"

Look at:

```text
dashboard/app/api_client.py
```

### "Change application configuration"

Look at:

```text
api/app/core/
dashboard/app/config.py
.env.example
```

### "Test something"

Look at:

```text
api/scripts/
dashboard/scripts/
```

---

# 29. Simple Mental Model

Think of the system like this:

```text
ROUTER
"What API URL was called?"
        ↓

SCHEMA
"What data came in?"
        ↓

SERVICE
"What should the system do?"
        ↓

MODEL
"What should be read/written in PostgreSQL?"
```

For the Dashboard:

```text
HTML Template
      ↓
Dashboard Route
      ↓
API Client
      ↓
Marketing API
```

For n8n:

```text
n8n Workflow
      ↓
Marketing API
      ↓
PostgreSQL
```

---

# 30. Before Changing Anything

Before starting a task:

```bash
git switch develop
git pull
git switch -c feature/task-name
```

Then identify which part of the system the task belongs to.

Do not randomly modify files until you understand which layer is responsible.

---

# 31. When You Finish

Test your changes locally.

Then:

```bash
git status
git add .
git commit -m "describe your change"
git push
```

After pushing:

```text
STOP.
```

Send the branch name to the project owner.

Do not create a Pull Request unless instructed.

Do not merge anything yourself.

---

# Most Important Rules

```text
Do not edit main directly.

Do not edit develop directly.

Always use a feature branch.

Do not commit secrets.

Do not connect directly to PostgreSQL.

Do not modify PROD.

Test your changes before pushing.

Push your branch and wait for review.
```