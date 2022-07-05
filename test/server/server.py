from fastapi import Depends, FastAPI, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

app = FastAPI()

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


@app.get("/secured", status_code=200)
async def read_secure_data(response: Response, auth: HTTPBasicCredentials = Depends(basic_auth_scheme)):
    if auth.username != 'se§ure' or auth.password != 's§cröt':
        response.status_code = 403
        return 'forbidden'
    return 'allowed'