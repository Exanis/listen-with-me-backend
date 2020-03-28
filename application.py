from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute
from starlette.middleware import Middleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
import config
from views import Server


ROUTES = [
    WebSocketRoute('/ws', Server)
]


MIDDLEWARES = [
    Middleware(CORSMiddleware, allow_origins=config.CORS_ORIGIN),
    Middleware(GZipMiddleware),
]

if not config.DEBUG:
    MIDDLEWARES.append(Middleware(HTTPSRedirectMiddleware))
    MIDDLEWARES.append(Middleware(TrustedHostMiddleware, allowed_hosts=config.ALLOWED_HOSTS))


app = Starlette(debug=config.DEBUG, routes=ROUTES)
app.state.config = config

@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()
