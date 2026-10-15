from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder

from crossst.api.schemas import AnalyzeRequest
from crossst.agent import run_batch_analysis

router = APIRouter(tags=["analysis"])


@router.post("/analyze")
def analyze_logs(request: AnalyzeRequest) -> dict[str, object]:
    try:
        result = run_batch_analysis(request)
        return jsonable_encoder(result)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError, NotImplementedError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
