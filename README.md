# AI Newsletter

AI news collection, classification, and subscriber delivery application.

- [Web app and API setup](docs/SETUP.md)
- [News collector setup and source configuration](docs/COLLECTOR.md)
- [Test real collection with Postman](docs/POSTMAN.md)
- `schema.sql` and root `models.py`: canonical PostgreSQL pipeline schema
- `collector/`: scheduled RSS, API (including Bluesky), and permitted HTML collection
- `api/` and `web/`: FastAPI and React subscriber application
- `NewsDistribution/`: delivery adapters

The API currently uses a separate prototype database schema. See the collector
guide before configuring database URLs; these schemas still need to be unified.
