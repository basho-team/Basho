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


READ_ROUTES = (
    "/api/v1/projects/{project_id}",
    "/api/v1/projects/{project_id}/pending",
    "/api/v1/projects/{project_id}/dossier",
    "/api/v1/reports/{report_version_id}",
)


def test_openapi_reads_declare_identity_headers(valid_env: dict[str, str]) -> None:
    # Act
    schema = create_app().openapi()

    # Assert: o BFF manda os mesmos headers X-Basho-* nas leituras
    for path in READ_ROUTES:
        names = {param["name"] for param in schema["paths"][path]["get"]["parameters"]}
        assert {"X-Basho-User-Id", "X-Basho-Role", "X-Basho-Identity-Secret"} <= names, path
