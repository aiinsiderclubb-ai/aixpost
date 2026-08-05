# 🚀 AIPostX - Production Ready SaaS Platform

## 📋 Overview

A **complete enterprise-grade SaaS platform** for Facebook group mass messaging with multi-tenant architecture, subscription management, and full automation.

### ✨ **Key Features**

#### 🏢 **Multi-Tenant SaaS**
- ✅ **User Registration & Authentication** with JWT
- ✅ **Role-based Access Control** (User, Admin)
- ✅ **Email Verification** and Password Reset
- ✅ **Subscription Management** with Stripe integration
- ✅ **Usage Tracking** and Limits enforcement

#### 💰 **Monetization & Billing**
- ✅ **3-Tier Subscription Plans** (Free, Plus $49, Premium $99)
- ✅ **Stripe Payment Integration** with webhooks
- ✅ **Automatic Billing** and subscription management
- ✅ **Usage-based Limitations** enforcement
- ✅ **Payment History** and invoice management

#### 📤 **Advanced Posting System**
- ✅ **Multi-User Facebook Posting** with session isolation
- ✅ **Campaign Management** with scheduling
- ✅ **Template System** with variables
- ✅ **Real-time Progress Tracking**
- ✅ **Advanced Analytics** and reporting

#### 🛠 **Enterprise Features**
- ✅ **Admin Dashboard** for user management
- ✅ **API-First Architecture** with rate limiting
- ✅ **Background Tasks** with Celery
- ✅ **Redis Caching** and session management
- ✅ **PostgreSQL Database** with proper indexing
- ✅ **Email Notifications** via SendGrid

---

## 🏗️ **Architecture**

### **Technology Stack**
- **Backend**: Flask, SQLAlchemy, PostgreSQL
- **Authentication**: JWT, Flask-JWT-Extended
- **Payments**: Stripe API
- **Background Tasks**: Celery + Redis
- **Email**: SendGrid
- **Frontend**: React/Vue.js (separate repo)
- **Deployment**: Docker, Docker Compose

### **System Architecture**
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Frontend      │    │    API Gateway   │    │   Database      │
│   (React/Vue)   │◄──►│   (Flask API)    │◄──►│  (PostgreSQL)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                       ┌────────▼────────┐
                       │     Redis       │
                       │  (Cache/Queue)  │
                       └─────────────────┘
                                │
                       ┌────────▼────────┐
                       │  Celery Workers │
                       │ (Facebook Bot)  │
                       └─────────────────┘
```

---

## 🚀 **Quick Start**

### **1. Prerequisites**
```bash
# Install dependencies
- Python 3.11+
- PostgreSQL 13+
- Redis 6+
- Chrome/Chromium browser
```

### **2. Environment Setup**
```bash
# Clone repository
git clone <your-repo-url>
cd facebook-saas-platform

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements_saas.txt
```

### **3. Database Setup**
```bash
# Start PostgreSQL and Redis
sudo systemctl start postgresql redis

# Create database
createdb facebook_saas_dev

# Set environment variables (copy .env.example to .env)
export DATABASE_URL="postgresql://username:password@localhost/facebook_saas_dev"
export REDIS_URL="redis://localhost:6379/0"
export SECRET_KEY="your-secret-key"

# Initialize database
python run.py init-db

# Create admin user
python run.py create-admin
```

### **4. Start Services**
```bash
# Terminal 1: Start main application
python run.py runserver --host 0.0.0.0 --port 5000

# Terminal 2: Start Celery worker
python run.py worker

# Terminal 3: Start Celery beat (scheduler)
python run.py beat

# Terminal 4: Start Flower (monitoring)
python run.py flower
```

### **5. Access Application**
- **API**: http://localhost:5000/api/v1
- **Health**: http://localhost:5000/health
- **Flower**: http://localhost:5555

---

## 📊 **API Documentation**

### **Authentication Endpoints**
```bash
POST /api/v1/auth/register     # User registration
POST /api/v1/auth/login        # User login
POST /api/v1/auth/logout       # User logout
POST /api/v1/auth/refresh      # Refresh token
POST /api/v1/auth/forgot-password  # Password reset
GET  /api/v1/auth/me          # Current user info
```

### **Subscription Management**
```bash
GET  /api/v1/billing/plans          # Available plans
POST /api/v1/billing/subscribe      # Create subscription
POST /api/v1/billing/cancel         # Cancel subscription
GET  /api/v1/billing/history        # Payment history
POST /api/v1/billing/webhook        # Stripe webhooks
```

### **Posting & Campaigns**
```bash
GET  /api/v1/posting/campaigns      # User campaigns
POST /api/v1/posting/campaigns      # Create campaign
PUT  /api/v1/posting/campaigns/:id  # Update campaign
POST /api/v1/posting/start/:id      # Start campaign
GET  /api/v1/posting/groups         # User groups
POST /api/v1/posting/fetch-groups   # Fetch FB groups
```

### **Admin Endpoints**
```bash
GET  /api/v1/admin/users            # All users
GET  /api/v1/admin/analytics        # Platform analytics
PUT  /api/v1/admin/users/:id        # Update user
DELETE /api/v1/admin/users/:id      # Delete user
```

---

## 💰 **Subscription Plans**

### **Free Plan** - $0/month
- ✅ 50 messages per month
- ✅ Up to 10 groups
- ✅ Basic posting
- ✅ Email support

### **Plus Plan** - $49/month
- ✅ 500 messages per month
- ✅ Up to 100 groups
- ✅ Advanced posting
- ✅ Message templates
- ✅ Basic analytics
- ✅ Priority support

### **Premium Plan** - $99/month
- ✅ 2000 messages per month
- ✅ Up to 500 groups
- ✅ Unlimited campaigns
- ✅ Advanced templates
- ✅ Full analytics
- ✅ API access
- ✅ VIP support

---

## 🔧 **Configuration**

### **Environment Variables**
```bash
# Core Configuration
FLASK_ENV=production
DATABASE_URL=postgresql://user:pass@host:5432/db
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-secret-key

# Stripe Configuration
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLIC_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Email Configuration
MAIL_USERNAME=your-sendgrid-api-key
MAIL_PASSWORD=your-sendgrid-password

# Admin Configuration
ADMIN_EMAILS=admin@yourcompany.com
```

### **Database Migrations**
```bash
# Create migration
flask db migrate -m "Description"

# Apply migration
flask db upgrade

# Rollback migration
flask db downgrade
```

---

## 🐳 **Docker Deployment**

### **Development with Docker Compose**
```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### **Production Deployment**
```bash
# Build production image
docker build -t facebook-saas:latest .

# Run with environment variables
docker run -d \
  --name facebook-saas \
  -p 5000:5000 \
  -e DATABASE_URL=$DATABASE_URL \
  -e REDIS_URL=$REDIS_URL \
  facebook-saas:latest
```

---

## 📈 **Monitoring & Analytics**

### **Built-in Monitoring**
- ✅ **Health Checks** at `/health`
- ✅ **Prometheus Metrics** for monitoring
- ✅ **Sentry Integration** for error tracking
- ✅ **Flower Dashboard** for Celery monitoring

### **Key Metrics**
- User registration and retention
- Subscription conversion rates
- Message sending success rates
- System performance and uptime
- Revenue and billing analytics

---

## 🧪 **Testing**

```bash
# Run all tests
python run.py test

# Run specific test file
pytest tests/test_auth.py -v

# Run with coverage
pytest --cov=app tests/

# Run integration tests
pytest tests/integration/ -v
```

---

## 🔒 **Security Features**

### **Authentication & Authorization**
- ✅ **JWT Token Authentication** with refresh tokens
- ✅ **Password Hashing** with bcrypt
- ✅ **Rate Limiting** on sensitive endpoints
- ✅ **CORS Configuration** for frontend integration
- ✅ **Input Validation** and sanitization

### **Data Protection**
- ✅ **Encrypted Credentials** storage
- ✅ **SQL Injection Protection** via SQLAlchemy
- ✅ **XSS Protection** with input sanitization
- ✅ **CSRF Protection** for forms
- ✅ **Secure Headers** configuration

---

## 📦 **Deployment Guide**

### **VPS Deployment**
```bash
# 1. Setup server
sudo apt update && sudo apt install -y python3 python3-pip postgresql redis-server nginx

# 2. Install dependencies
pip3 install -r requirements_saas.txt

# 3. Configure services
sudo systemctl enable postgresql redis-server nginx

# 4. Setup database
sudo -u postgres createdb facebook_saas
python run.py init-db

# 5. Configure Nginx
# Add nginx configuration for reverse proxy

# 6. Start application with Gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app()"
```

### **Cloud Deployment (AWS/GCP)**
- Use managed PostgreSQL (RDS/Cloud SQL)
- Use managed Redis (ElastiCache/Memorystore)
- Deploy with container services (ECS/Cloud Run)
- Setup load balancer and auto-scaling

---

## 🤝 **Contributing**

### **Development Workflow**
1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Make changes and add tests
4. Run test suite (`python run.py test`)
5. Commit changes (`git commit -m 'Add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open Pull Request

### **Code Standards**
- Follow PEP 8 style guidelines
- Add docstrings to all functions
- Include unit tests for new features
- Update documentation as needed

---

## 📝 **License**

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🆘 **Support**

### **Documentation**
- 📖 **API Docs**: `/api/v1/docs`
- 🔧 **Configuration Guide**: See environment variables section
- 🐛 **Troubleshooting**: Check logs and error messages

### **Contact**
- 📧 **Email**: support@yourcompany.com
- 💬 **Discord**: [Your Discord Server]
- 🐛 **Issues**: [GitHub Issues](https://github.com/youruser/repo/issues)

---

## 🎉 **Production Ready Features**

| Feature | Status | Description |
|---------|--------|-------------|
| 🔐 **Multi-tenant Auth** | ✅ Complete | JWT authentication with roles |
| 💳 **Stripe Integration** | ✅ Complete | Full payment processing |
| 📊 **Usage Tracking** | ✅ Complete | Plan limits enforcement |
| 🤖 **Facebook Automation** | ✅ Complete | Multi-user posting system |
| 📈 **Analytics Dashboard** | ✅ Complete | User and admin analytics |
| 🔄 **Background Tasks** | ✅ Complete | Celery task processing |
| 📧 **Email System** | ✅ Complete | SendGrid integration |
| 🛡️ **Security** | ✅ Complete | Enterprise-grade security |
| 🐳 **Docker Support** | ✅ Complete | Container deployment |
| 📱 **API-First** | ✅ Complete | RESTful API design |

**🚀 Ready for production deployment and scaling!** 