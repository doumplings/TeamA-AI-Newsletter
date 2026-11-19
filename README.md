# AI Newsletter

AI news collection, classification, and subscriber delivery application.

- [Setup: database, API, worker and web app](docs/SETUP.md)
- [Pipeline worker: scheduler, classifier, dispatcher](docs/PIPELINE.md)
- [News collector and source configuration](docs/COLLECTOR.md)
- [Test real collection with Postman](docs/POSTMAN.md)
- `schema.sql` and root `models.py`: canonical PostgreSQL pipeline schema
- `init_db.py`: creates the schema and default data on a new database, local or hosted
- `scheduler/`: the worker; runs the scrape, classify and dispatch cycles on their intervals
- `collector/`: RSS, API (including Bluesky), and permitted HTML collection; same-story check
- `classifier/`: importance score and level for each new item
- `notifier/`: queues deliveries for subscribers, sends them, retries failures
- `api/` and `web/`: FastAPI and React subscriber application, with source administration
- `NewsDistribution/`: earlier standalone Discord adapter

The API and the worker share one PostgreSQL database and one `.env` at the repo root.

```bash
cp .env.example .env            # set DATABASE_URL and SECRET_KEY
python init_db.py               # tables, default sources, scoring rules
python -m scheduler             # the worker
python -m uvicorn app.main:app --app-dir api --port 8000
cd web && npm install && npm run dev
```
