facebook_saas/
├── app/                          # Main application
│   ├── __init__.py
│   ├── config.py                 # Configuration
│   ├── models/                   # Database models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── subscription.py
│   │   ├── posting.py
│   │   └── analytics.py
│   ├── auth/                     # Authentication
│   │   ├── __init__.py
│   │   ├── views.py
│   │   ├── utils.py
│   │   └── decorators.py
│   ├── api/                      # API endpoints
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── posting.py
│   │   ├── billing.py
│   │   └── admin.py
│   ├── services/                 # Business logic
│   │   ├── __init__.py
│   │   ├── user_service.py
│   │   ├── posting_service.py
│   │   ├── billing_service.py
│   │   └── analytics_service.py
│   ├── tasks/                    # Celery tasks
│   │   ├── __init__.py
│   │   ├── posting_tasks.py
│   │   └── billing_tasks.py
│   ├── utils/                    # Utilities
│   │   ├── __init__.py
│   │   ├── decorators.py
│   │   ├── helpers.py
│   │   └── validators.py
│   └── templates/                # Email templates
│       ├── auth/
│       └── billing/
├── bot/                          # Existing bot code (refactored)
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── base_poster.py        # Refactored FacebookGroupPoster
│   │   ├── group_fetcher.py      # Refactored fetcher
│   │   └── template_manager.py   # Refactored templates
│   └── adapters/
│       ├── __init__.py
│       └── facebook_adapter.py   # Facebook-specific logic
├── frontend/                     # Frontend application
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   └── utils/
│   ├── package.json
│   └── vite.config.js
├── migrations/                   # Database migrations
├── tests/                        # Test suite
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── docker/                       # Docker configurations
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── docker-compose.prod.yml
├── scripts/                      # Deployment scripts
├── docs/                         # Documentation
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── run.py                        # Application entry point 