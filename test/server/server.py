from fastapi import FastAPI, Security, Depends, HTTPException
from fastapi.security.api_key import APIKeyQuery, APIKey

API_KEY_NAME="private_token"
API_KEY="super-duper-secret"
api_key_query = APIKeyQuery(name=API_KEY_NAME, auto_error=True)

app = FastAPI()

def get_api_key (api_key_query: str = Security(api_key_query)):
    if api_key_query == API_KEY:
      return api_key_query
    else:
      raise HTTPException(403)

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


@app.get("/200/api-key")
def read_root(api_key: APIKey = Depends(get_api_key)):
    return 200
