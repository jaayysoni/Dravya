from fastapi import FastAPI
from app.routes.users import router as users_router
from app.routes.events import router as events_router
from app.routes.donors import router as donors_router
from app.routes.pledges import router as pledges_router
from app.routes.payments import router as payments_router
from app.routes.family import router as families_router

app = FastAPI()

app.include_router(users_router)
app.include_router(events_router)
app.include_router(donors_router)
app.include_router(pledges_router)
app.include_router(payments_router)
app.include_router(families_router)