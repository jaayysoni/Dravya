from fastapi import FastAPI
from app.routes.users import router as users_router
from app.routes.events import router as events_router

app = FastAPI()

app.include_router(users_router)
app.include_router(events_router)