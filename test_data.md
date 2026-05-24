## Test Data

### Commands to reset after docker compose down -v
1. python3 seed_reels.py
2. curl -X POST http://localhost:8000/v1/goals_embedding -H "Content-Type: application/json" -d '{"goals": ["fitness", "coding", "reading"]}'
3. update user_id below

### Current test user
user_id: 9ef7c9ac-5535-426f-bbc5-8fa7b7e62e42
goals: fitness, coding, reading

### Endpoints
POST /v1/goals_embedding     - onboard user
GET  /v1/feed_return         - get feed
POST /v1/upload_reel         - upload reel
GET  /v1/celery_status/{id}  - check upload status
POST /v1/tasks               - create task
PATCH /v1/tasks/{id}/complete - complete task
POST /v1/agent/past_tasks    - get similar past tasks