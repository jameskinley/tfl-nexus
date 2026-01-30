# TfL Nexus Dashboard

A beautiful, lightweight Flask dashboard for visualizing real-time TfL delay data.

## Features

- 🎨 Modern, animated UI with TfL-inspired design
- 📊 Real-time delay monitoring
- 🔄 Auto-refresh every 30 seconds
- 📈 Severity breakdown and statistics
- 🌙 Dark theme with glassmorphism effects
- ⚡ Lightweight and fast

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure your `.env` file in the parent directory has the correct database credentials:
```
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_USER=sa
POSTGRES_PASSWORD=password
POSTGRES_DB=tflnexus
```

3. Run the dashboard:
```bash
python app.py
```

4. Open your browser to: `http://localhost:5000`

## API Endpoints

- `GET /` - Main dashboard interface
- `GET /api/delays/current` - Get current delays from the last hour
- `GET /api/delays/summary` - Get summary statistics by line
- `GET /api/delays/severity-breakdown` - Get breakdown by severity
- `GET /api/health` - Health check endpoint

## Tech Stack

- **Backend**: Flask, SQLAlchemy, PostgreSQL
- **Frontend**: Vanilla JS, CSS3 (animations, gradients, glassmorphism)
- **Database**: PostgreSQL with PostGIS (via existing setup)
