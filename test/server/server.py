from fastapi import Depends, FastAPI, status, HTTPException
from fastapi.logger import logger
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from starlette.responses import PlainTextResponse

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

basic_auth_scheme = HTTPBasic()


@app.get("/", status_code=200)
def read_root():
    return 200


@app.get("/200", status_code=200)
def read_root():
    return 200


@app.get("/404", status_code=404)
async def read_item():
    return 404


@app.get("/500", status_code=500)
async def read_item():
    return 500


@app.post("/503", status_code=503)
async def read_item():
    return 503


@app.get("/secured", status_code=200, response_class=PlainTextResponse)
async def read_secure_data(basic_auth: HTTPBasicCredentials = Depends(basic_auth_scheme)):
    if basic_auth.username != 'user1' or basic_auth.password != 'abcdefghijklmnopqrstuvwxyz':
        logger.warning("[WARN] wrong auth: %s : %s ", basic_auth.username, basic_auth.password)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Incorrect user (${basic_auth.username}) or password (${basic_auth.password})",
            headers={"WWW-Authenticate": "Basic"},
        )
    return 'allowed'