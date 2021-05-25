from fastapi import FastAPI
import uvicorn

app = FastAPI()


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
