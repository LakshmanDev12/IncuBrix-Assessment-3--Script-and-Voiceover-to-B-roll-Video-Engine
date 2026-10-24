from app.main import app

def test_openapi_schema_generated():
    schema = app.openapi()
    assert schema is not None
    assert schema["info"]["title"] == "Script and Voiceover to B-roll Video Engine"
    assert schema["info"]["version"] == "1.0.0"
    
    # Check key endpoints exist in schema
    paths = schema["paths"]
    assert "/v1/jobs" in paths
    assert "post" in paths["/v1/jobs"]
    assert "/v1/jobs/multipart" in paths
    assert "/v1/jobs/{job_id}" in paths
    assert "/v1/jobs/{job_id}/cancel" in paths
    assert "/v1/jobs/{job_id}/artifacts" in paths
    assert "/v1/jobs/{job_id}/artifacts/{artifact_name}" in paths
    assert "/v1/limits" in paths
    assert "/health" in paths

    # Check components and schemas
    components = schema["components"]["schemas"]
    assert "RenderJobCreate" in components
    assert "JobResponse" in components
    assert "LimitsResponse" in components
    assert "ArtifactsResponse" in components
    assert "CancelJobResponse" in components
