"""
FastAPI REST API

REST API for batch processing NSNs.
"""

from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core import scrape_batch, flatten_batch_results


# Pydantic models for API
class BatchRequest(BaseModel):
    """Request body for batch processing."""
    nsns: List[str] = Field(..., description="List of NSNs to process")


class SupplierRow(BaseModel):
    """Flat supplier row in response."""
    nsn: str
    open_status: str
    supplier_name: str
    cage_code: str
    email: str
    phone: str


class BatchSummary(BaseModel):
    """Summary statistics for batch processing."""
    total_nsns: int
    total_rows: int
    successful: int
    failed: int


class BatchResponse(BaseModel):
    """Response body for batch processing."""
    results: List[SupplierRow]
    summary: BatchSummary


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    message: str


# Create FastAPI app
app = FastAPI(
    title="RFQ Automation API",
    description="REST API for batch processing NSNs and discovering supplier contacts",
    version="1.0.0"
)

# Add CORS middleware for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        message="RFQ Automation API is running"
    )


@app.post("/api/batch", response_model=BatchResponse)
async def process_batch(request: BatchRequest):
    """
    Process a batch of NSNs.

    Accepts a list of NSNs and returns flattened supplier data with one row per supplier.
    If an NSN has multiple suppliers, it will appear multiple times in the results.

    Args:
        request: BatchRequest containing list of NSNs

    Returns:
        BatchResponse with flattened results and summary statistics
    """
    if not request.nsns:
        raise HTTPException(status_code=400, detail="No NSNs provided")

    if len(request.nsns) > 500:
        raise HTTPException(
            status_code=400,
            detail="Maximum 500 NSNs per batch request"
        )

    # Process batch
    batch_result = await scrape_batch(request.nsns)

    # Flatten results
    flat_rows = flatten_batch_results(batch_result)

    # Convert to response format
    supplier_rows = [
        SupplierRow(
            nsn=row["nsn"],
            open_status=row["open_status"],
            supplier_name=row["supplier_name"],
            cage_code=row["cage_code"],
            email=row["email"],
            phone=row["phone"]
        )
        for row in flat_rows
    ]

    return BatchResponse(
        results=supplier_rows,
        summary=BatchSummary(
            total_nsns=batch_result.total_nsns,
            total_rows=len(flat_rows),
            successful=batch_result.successful,
            failed=batch_result.failed
        )
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
