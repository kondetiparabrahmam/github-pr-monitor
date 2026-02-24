"""
AWS Lambda Management API
==========================
Real-time Python API for managing AWS Lambda functions
Works with both LocalStack (local practice) and Real AWS

Install dependencies:
    pip install fastapi uvicorn boto3 python-multipart

Run:
    uvicorn lambda_api:app --reload --port 8000

LocalStack Setup:
    localstack start
    Set USE_LOCALSTACK=true in environment or change config below
"""

import boto3
import json
import zipfile
import io
import os
from datetime import datetime
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional
import uvicorn

# ============================================================
# CONFIG - Change USE_LOCALSTACK to False for real AWS
# ============================================================
USE_LOCALSTACK = True  # Set to False for real AWS

LOCALSTACK_ENDPOINT = "http://localhost:4566"
AWS_REGION = "us-east-1"
AWS_ACCESS_KEY = "test"       # For LocalStack (any value works)
AWS_SECRET_KEY = "test"       # For LocalStack (any value works)


def get_lambda_client():
    """Get boto3 Lambda client (LocalStack or Real AWS)"""
    if USE_LOCALSTACK:
        return boto3.client(
            "lambda",
            region_name=AWS_REGION,
            endpoint_url=LOCALSTACK_ENDPOINT,
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY,
        )
    else:
        # Real AWS - uses credentials from ~/.aws/credentials or env vars
        return boto3.client("lambda", region_name=AWS_REGION)


# ============================================================
# FastAPI App
# ============================================================
app = FastAPI(
    title="AWS Lambda Management API",
    description="Real-time API to manage AWS Lambda Functions",
    version="1.0.0"
)


# ============================================================
# REQUEST MODELS
# ============================================================
class CreateFunctionRequest(BaseModel):
    function_name: str
    runtime: str = "python3.11"           # e.g. python3.11, nodejs18.x, java11
    role_arn: str = "arn:aws:iam::000000000000:role/lambda-role"
    handler: str = "handler.lambda_handler"
    description: Optional[str] = "Created via Lambda API"
    timeout: int = 30                      # seconds (max 900)
    memory_size: int = 128                 # MB (128 to 10240)
    environment_vars: Optional[dict] = {}


class InvokeFunctionRequest(BaseModel):
    function_name: str
    payload: Optional[dict] = {}
    invocation_type: str = "RequestResponse"  # or "Event" (async)


class UpdateFunctionRequest(BaseModel):
    function_name: str
    timeout: Optional[int] = None
    memory_size: Optional[int] = None
    environment_vars: Optional[dict] = None
    description: Optional[str] = None


class AddTriggerRequest(BaseModel):
    function_name: str
    trigger_type: str        # "s3", "apigateway", "schedule"
    source_arn: Optional[str] = None
    schedule_expression: Optional[str] = "rate(5 minutes)"


# ============================================================
# REAL-TIME SCENARIO 1: Health Check
# ============================================================
@app.get("/")
def health_check():
    """Check if API and AWS connection is working"""
    try:
        client = get_lambda_client()
        client.list_functions(MaxItems=1)
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "mode": "LocalStack" if USE_LOCALSTACK else "Real AWS",
            "region": AWS_REGION
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AWS connection failed: {str(e)}")


# ============================================================
# REAL-TIME SCENARIO 2: List All Lambda Functions
# ============================================================
@app.get("/functions")
def list_functions():
    """
    List all Lambda functions
    Real-time use case: Dashboard showing all your deployed functions
    """
    try:
        client = get_lambda_client()
        response = client.list_functions()
        functions = response.get("Functions", [])

        result = []
        for fn in functions:
            result.append({
                "name": fn["FunctionName"],
                "runtime": fn.get("Runtime", "N/A"),
                "memory": fn.get("MemorySize", 128),
                "timeout": fn.get("Timeout", 3),
                "last_modified": fn.get("LastModified", "N/A"),
                "description": fn.get("Description", ""),
                "arn": fn.get("FunctionArn", ""),
                "state": fn.get("State", "Active")
            })

        return {
            "total": len(result),
            "functions": result,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# REAL-TIME SCENARIO 3: Get Function Details
# ============================================================
@app.get("/functions/{function_name}")
def get_function(function_name: str):
    """
    Get details of a specific Lambda function
    Real-time use case: Monitoring a specific function's config
    """
    try:
        client = get_lambda_client()
        response = client.get_function(FunctionName=function_name)
        config = response["Configuration"]

        return {
            "name": config["FunctionName"],
            "arn": config["FunctionArn"],
            "runtime": config.get("Runtime"),
            "handler": config.get("Handler"),
            "memory": config.get("MemorySize"),
            "timeout": config.get("Timeout"),
            "description": config.get("Description"),
            "last_modified": config.get("LastModified"),
            "state": config.get("State"),
            "environment": config.get("Environment", {}).get("Variables", {}),
            "code_size": config.get("CodeSize"),
        }
    except client.exceptions.ResourceNotFoundException:
        raise HTTPException(status_code=404, detail=f"Function '{function_name}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# REAL-TIME SCENARIO 4: Create Lambda Function
# ============================================================
@app.post("/functions/create")
def create_function(request: CreateFunctionRequest):
    """
    Create a new Lambda function with sample code
    Real-time use case: Auto-deploy a new microservice function
    """
    try:
        client = get_lambda_client()

        # Generate sample Python Lambda code
        sample_code = f'''
import json

def lambda_handler(event, context):
    """
    Auto-generated Lambda function: {request.function_name}
    Created: {datetime.now().isoformat()}
    """
    print("Event received:", json.dumps(event))
    
    return {{
        "statusCode": 200,
        "body": json.dumps({{
            "message": "Hello from {request.function_name}!",
            "event": event,
            "function": context.function_name if context else "{request.function_name}"
        }})
    }}
'''

        # Create ZIP file with the Lambda code
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr("handler.py", sample_code)
        zip_buffer.seek(0)

        # Create the Lambda function
        response = client.create_function(
            FunctionName=request.function_name,
            Runtime=request.runtime,
            Role=request.role_arn,
            Handler=request.handler,
            Code={"ZipFile": zip_buffer.read()},
            Description=request.description,
            Timeout=request.timeout,
            MemorySize=request.memory_size,
            Environment={"Variables": request.environment_vars or {}},
        )

        return {
            "message": f"Function '{request.function_name}' created successfully!",
            "function_arn": response.get("FunctionArn"),
            "runtime": response.get("Runtime"),
            "state": response.get("State"),
            "created_at": datetime.now().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# REAL-TIME SCENARIO 5: Upload Custom Lambda Code
# ============================================================
@app.post("/functions/{function_name}/upload")
async def upload_function_code(function_name: str, file: UploadFile = File(...)):
    """
    Upload a ZIP file as Lambda function code
    Real-time use case: Deploy your own Python code to Lambda
    """
    try:
        client = get_lambda_client()

        if not file.filename.endswith(".zip"):
            raise HTTPException(status_code=400, detail="Only .zip files are supported")

        zip_content = await file.read()

        response = client.update_function_code(
            FunctionName=function_name,
            ZipFile=zip_content,
        )

        return {
            "message": f"Code uploaded to '{function_name}' successfully!",
            "code_size": response.get("CodeSize"),
            "last_modified": response.get("LastModified"),
            "state": response.get("State")
        }

    except client.exceptions.ResourceNotFoundException:
        raise HTTPException(status_code=404, detail=f"Function '{function_name}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# REAL-TIME SCENARIO 6: Invoke Lambda Function
# ============================================================
@app.post("/functions/invoke")
def invoke_function(request: InvokeFunctionRequest):
    """
    Invoke a Lambda function and get response
    Real-time use case: Trigger a Lambda for processing (e.g., resize image, send email)
    """
    try:
        client = get_lambda_client()

        response = client.invoke(
            FunctionName=request.function_name,
            InvocationType=request.invocation_type,
            Payload=json.dumps(request.payload),
        )

        # Read the response payload
        payload = response["Payload"].read()
        result = json.loads(payload) if payload else {}

        return {
            "function_name": request.function_name,
            "status_code": response.get("StatusCode"),
            "invocation_type": request.invocation_type,
            "response": result,
            "executed_at": datetime.now().isoformat(),
            "error": response.get("FunctionError")
        }

    except client.exceptions.ResourceNotFoundException:
        raise HTTPException(status_code=404, detail=f"Function '{request.function_name}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# REAL-TIME SCENARIO 7: Update Function Config
# ============================================================
@app.put("/functions/update")
def update_function(request: UpdateFunctionRequest):
    """
    Update Lambda function configuration
    Real-time use case: Increase memory/timeout when function is slow
    """
    try:
        client = get_lambda_client()
        update_params = {"FunctionName": request.function_name}

        if request.timeout:
            update_params["Timeout"] = request.timeout
        if request.memory_size:
            update_params["MemorySize"] = request.memory_size
        if request.description:
            update_params["Description"] = request.description
        if request.environment_vars is not None:
            update_params["Environment"] = {"Variables": request.environment_vars}

        response = client.update_function_configuration(**update_params)

        return {
            "message": f"Function '{request.function_name}' updated successfully!",
            "timeout": response.get("Timeout"),
            "memory": response.get("MemorySize"),
            "last_modified": response.get("LastModified"),
            "state": response.get("State")
        }

    except client.exceptions.ResourceNotFoundException:
        raise HTTPException(status_code=404, detail=f"Function '{request.function_name}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# REAL-TIME SCENARIO 8: Delete Lambda Function
# ============================================================
@app.delete("/functions/{function_name}")
def delete_function(function_name: str):
    """
    Delete a Lambda function
    Real-time use case: Cleanup old/unused Lambda functions
    """
    try:
        client = get_lambda_client()
        client.delete_function(FunctionName=function_name)

        return {
            "message": f"Function '{function_name}' deleted successfully!",
            "deleted_at": datetime.now().isoformat()
        }

    except client.exceptions.ResourceNotFoundException:
        raise HTTPException(status_code=404, detail=f"Function '{function_name}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# REAL-TIME SCENARIO 9: Get Function Logs (CloudWatch)
# ============================================================
@app.get("/functions/{function_name}/logs")
def get_function_logs(function_name: str, limit: int = 20):
    """
    Get recent CloudWatch logs for a Lambda function
    Real-time use case: Debugging why a Lambda function is failing
    """
    try:
        if USE_LOCALSTACK:
            logs_client = boto3.client(
                "logs",
                region_name=AWS_REGION,
                endpoint_url=LOCALSTACK_ENDPOINT,
                aws_access_key_id=AWS_ACCESS_KEY,
                aws_secret_access_key=AWS_SECRET_KEY,
            )
        else:
            logs_client = boto3.client("logs", region_name=AWS_REGION)

        log_group = f"/aws/lambda/{function_name}"

        # Get log streams
        streams = logs_client.describe_log_streams(
            logGroupName=log_group,
            orderBy="LastEventTime",
            descending=True,
            limit=5
        )

        all_logs = []
        for stream in streams.get("logStreams", []):
            events = logs_client.get_log_events(
                logGroupName=log_group,
                logStreamName=stream["logStreamName"],
                limit=limit
            )
            for event in events.get("events", []):
                all_logs.append({
                    "timestamp": datetime.fromtimestamp(event["timestamp"] / 1000).isoformat(),
                    "message": event["message"].strip()
                })

        return {
            "function_name": function_name,
            "log_group": log_group,
            "total_logs": len(all_logs),
            "logs": all_logs[:limit]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not fetch logs: {str(e)}")


# ============================================================
# REAL-TIME SCENARIO 10: List Function Versions
# ============================================================
@app.get("/functions/{function_name}/versions")
def list_versions(function_name: str):
    """
    List all versions of a Lambda function
    Real-time use case: Rollback to previous version if new deploy fails
    """
    try:
        client = get_lambda_client()
        response = client.list_versions_by_function(FunctionName=function_name)
        versions = response.get("Versions", [])

        return {
            "function_name": function_name,
            "total_versions": len(versions),
            "versions": [
                {
                    "version": v.get("Version"),
                    "description": v.get("Description"),
                    "last_modified": v.get("LastModified"),
                    "code_size": v.get("CodeSize")
                }
                for v in versions
            ]
        }

    except client.exceptions.ResourceNotFoundException:
        raise HTTPException(status_code=404, detail=f"Function '{function_name}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Run the app
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  AWS Lambda Management API")
    print(f"  Mode: {'LocalStack (Local Practice)' if USE_LOCALSTACK else 'Real AWS'}")
    print(f"  Region: {AWS_REGION}")
    print("  Docs: http://localhost:8000/docs")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)