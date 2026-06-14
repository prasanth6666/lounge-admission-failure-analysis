from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from models import AdmissionTransaction
from service import analyse_transaction

app = FastAPI(
    title="Lounge Admission Failure Analysis Service",
    description="Analyses failed lounge admission transactions using deterministic rules and LLM-generated guidance.",
    version="1.0.0",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    sanitized = [
        {"type": e["type"], "loc": e["loc"], "msg": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": sanitized})


@app.post("/analyse")
def analyse(transaction: AdmissionTransaction):
    response = analyse_transaction(transaction)
    return JSONResponse(content=response)


@app.get("/health")
def health():
    return {"status": "ok"}
