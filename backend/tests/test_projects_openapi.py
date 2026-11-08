"""O OpenAPI expõe o contrato de projetos (#5) que o frontend usa para gerar tipos."""

from basho.main import create_app

PROJECT_ROUTES = {
    ("/api/v1/projects/{project_id}", "get"),
    ("/api/v1/projects/{project_id}/pending", "get"),
    ("/api/v1/projects/{project_id}/dossier", "get"),
    ("/api/v1/pending/{pending_id}/answer", "post"),
    ("/api/v1/artifacts/{artifact_id}/approval", "post"),
}


def test_openapi_has_project_routes_and_conflict_schema(valid_env: dict[str, str]) -> None:
    # Act
    schema = create_app().openapi()

    # Assert
    routes = {(path, method) for path, item in schema["paths"].items() for method in item}
    assert routes >= PROJECT_ROUTES
    approval = schema["paths"]["/api/v1/artifacts/{artifact_id}/approval"]["post"]
    assert set(approval["responses"]) >= {"201", "409", "422"}
    assert {"ProjectOut", "PendingPageOut", "DossierOut", "ConflictOut"} <= set(
        schema["components"]["schemas"]
    )
