from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from app.routes.users import router as users_router
from app.routes.events import router as events_router
from app.routes.donors import router as donors_router
from app.routes.pledges import router as pledges_router
from app.routes.payments import router as payments_router
from app.routes.family import router as families_router
from app.routes.dashboard import router as dashboard_router

app = FastAPI()

templates = Jinja2Templates(directory="templates")

# ── HTML page routes ──
@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")

@app.get("/donors", response_class=HTMLResponse)
def donors_page(request: Request):
    return templates.TemplateResponse(request, "donor.html")

@app.get("/events/create", response_class=HTMLResponse)
def create_event_page(request: Request):
    return templates.TemplateResponse(request, "create_event.html")

@app.get("/events/{event_id}", response_class=HTMLResponse)
def event_detail_page(request: Request, event_id: int):
    return templates.TemplateResponse(request, "event.html")

# ── API routers ──
app.include_router(users_router)
app.include_router(events_router)
app.include_router(donors_router)
app.include_router(pledges_router)
app.include_router(payments_router)
app.include_router(families_router)
app.include_router(dashboard_router)