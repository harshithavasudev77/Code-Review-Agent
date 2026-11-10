# FastAPI OAuth2 tutorial

**Decision:** pending
**Review complete:** yes
**Human review required:** yes
**Provider / model:** Nebius Token Factory / `nvidia/Nemotron-3_5-Lightning`
**Run:** `63147a1c-4b98-4511-8978-4de7520dad3a` · 2026-11-09T06:13:07.151283+00:00
**Source:** https://github.com/fastapi/fastapi @ 0.115.0
**Elapsed:** 20.2s · **LLM requests:** 10 · **Tokens:** 27,932 input / 4,661 output

## Assessment

The FastAPI OAuth2 tutorial snapshot demonstrates a basic OAuth2PasswordBearer pattern with no critical or high-severity vulnerabilities. The tutorial correctly shows the oauth2_scheme dependency and test cases for missing/valid/incorrect tokens and OpenAPI schema output. Medium-severity findings highlight that the tokenUrl is hardcoded to 'token' with no corresponding route defined, the response echoes the raw token without validation, and the test suite lacks coverage for token refresh/revocation, empty Bearer tokens, and security enforcement. Low-severity findings note test fragility (incorrect token header format missing 'Bearer' prefix), missing rate-limiting on token endpoints, and OpenAPI scope not validated against the dependency. The specialist summaries confirm no critical/high bugs were found; all findings are within tutorial scope and relate to missing production hardening or test coverage gaps.

critical: 0 · high: 0 · medium: 4 · low: 5 · info: 2

## Prioritized findings

### CR-002 · MEDIUM · OAuth2PasswordBearer tokenUrl hardcoded to 'token' endpoint with no corresponding route defined

`docs_src/security/tutorial001.py:6-6` · Agents: bugs · Confidence: 85%

The OAuth2PasswordBearer instance is configured with tokenUrl='token', but no route handler for '/token' is defined in this tutorial file. FastAPI will generate an OpenAPI security scheme pointing at that URL, and the OAuth2 flow will attempt to retrieve a token from that endpoint at runtime. Without a token endpoint, any request using password grant will fail with a 401 or unhandled error depending on client behavior.

**Source evidence**

````text
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
````

**Recommendation:** Add a token endpoint example or document that tokenUrl points to an external authentication service. For a minimal tutorial, consider omitting the tokenUrl parameter so FastAPI uses the default '/oauth2/token'.

**Suggested test:** Add a test that requests '/items' with an Authorization Bearer header and verifies the 401 response when no token endpoint is registered, confirming the scheme falls back to default behavior or returns a clear error.

### CR-001 · MEDIUM · Test covers only happy-path and basic error cases for token presence

`tests/test_tutorial/test_security/test_tutorial001.py:15-18` · Agents: security · Confidence: 95%

The test_token test only verifies that a Bearer token results in 200 and the token echo. It does not test token validation, expiration, revocation, or scope checks. As a tutorial test this is expected, but a production test suite would include negative cases for invalid tokens.

**Source evidence**

````text
def test_token():
    response = client.get("/items", headers={"Authorization": "Bearer testtoken"})
    assert response.status_code == 200, response.text
    assert response.json() == {"token": "testtoken"}
````

**Recommendation:** Add tests for token validation failure (e.g., wrong signature, expired token) and for missing/incorrect Authorization header format. Ensure the test suite covers both the dependency's automatic 401 and manual token verification failures.

**Suggested test:** Add a test that sends an invalid/expired token and expects 401/403; add a test for malformed Authorization header (e.g., 'Basic xyz').

### CR-003 · MEDIUM · OpenAPI security scheme references undefined 'token' flow endpoint

`tests/test_tutorial/test_security/test_tutorial001.py:51-53` · Agents: bugs · Confidence: 85%

The generated OpenAPI schema declares an OAuth2 password flow with tokenUrl='token'. Since no '/token' route exists in the tutorial app, the schema describes a non-functional endpoint. Consumers importing this schema will see a password flow with no corresponding server operation, which is misleading and may cause tooling errors.

**Source evidence**

````text
                "OAuth2PasswordBearer": {
                    "type": "oauth2",
                    "flows": {"password": {"scopes": {}, "tokenUrl": "token"}},
````

**Recommendation:** Either add a '/token' route to the FastAPI app, or remove the tokenUrl parameter from OAuth2PasswordBearer so the default '/oauth2/token' is used (and documented). If this is a deliberate placeholder, add a comment explaining the intent.

**Suggested test:** Generate openapi.json and assert that 'tokenUrl' points to a route that either exists in the app or is documented as external.

### CR-004 · MEDIUM · No test for token refresh / revocation flow

`tests/test_tutorial/test_security/test_tutorial001.py:1-57` · Agents: tests · Confidence: 70%

The tutorial introduces OAuth2PasswordBearer with tokenUrl="token" but no token endpoint or refresh/revocation logic is present. There is no test exercising token lifecycle beyond a single valid token.

**Source evidence**

````text
from fastapi.testclient import TestClient

from docs_src.security.tutorial001 import app

client = TestClient(app)


def test_no_token():
    response = client.get("/items")
    assert response.status_code == 401, response.text
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_token():
    response = client.get("/items", headers={"Authorization": "Bearer testtoken"})
    assert response.status_code == 200, response.text
    assert response.json() == {"token": "testtoken"}


def test_incorrect_token():
    response = client.get("/items", headers={"Authorization": "Notexistent testtoken"})
    assert response.status_code == 401, response.text
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_openapi_schema():
    response = client.get("/openapi.json")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "openapi": "3.1.0",
        "info": {"title": "FastAPI", "version": "0.1.0"},
        "paths": {
            "/items/": {
                "get": {
                    "responses": 
````

**Recommendation:** If a token endpoint is expected, add it to the tutorial code and corresponding tests for refresh and revocation. If the tutorial intentionally omits it, document the omission.

### CR-005 · LOW · Token value returned directly in response body without validation

`docs_src/security/tutorial001.py:10-11` · Agents: security · Confidence: 90%

The read_items endpoint echoes the raw token string into the JSON response. In a real application the token would be validated (e.g., JWT signature verification, introspection) before use. The tutorial omits validation for brevity.

**Source evidence**

````text
async def read_items(token: str = Depends(oauth2_scheme)):
    return {"token": token}
````

**Recommendation:** Add token validation logic (e.g., JWT decode with secret key, token introspection) before processing the token. Validate scope/claims as appropriate for the application.

**Suggested test:** Write a test that sends a malformed or tampered token and asserts a 401/403 response rather than the token being echoed.

### CR-006 · LOW · Missing test for Bearer scheme header when token is empty string

`tests/test_tutorial/test_security/test_tutorial001.py:8-12` · Agents: tests · Confidence: 90%

The test verifies the WWW-Authenticate header is "Bearer" when no token is provided, but does not test what happens when an empty Bearer token is sent (e.g., "Bearer " with no value). This is a bounded functional gap.

**Source evidence**

````text
def test_no_token():
    response = client.get("/items")
    assert response.status_code == 401, response.text
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers["WWW-Authenticate"] == "Bearer"
````

**Recommendation:** Add a test case that sends an Authorization header with only "Bearer " (no token) and asserts the server responds 401 and the detail message.

**Suggested test:** def test_empty_bearer_token(client):\n    response = client.get("/items", headers={"Authorization": "Bearer "})\n    assert response.status_code == 401\n    assert response.json() == {"detail": "Not authenticated"}\n    assert response.headers["WWW-Authenticate"] == "Bearer"

### CR-007 · LOW · No rate-limiting or brute-force mitigation on token endpoint

`docs_src/security/tutorial001.py:6-6` · Agents: security · Confidence: 85%

The tutorial does not configure any rate limiting, throttling, or brute-force protection on the token issuance endpoint. This is out of scope for an introductory example but should be considered for production deployment.

**Source evidence**

````text
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
````

**Recommendation:** If a token endpoint is added, integrate rate limiting (e.g., SlowAPI, Depends with custom limiter) and consider account lockout policies after repeated failures.

### CR-008 · LOW · OpenAPI schema security scope not validated against actual dependency

`tests/test_tutorial/test_security/test_tutorial001.py:28-57` · Agents: tests · Confidence: 80%

The test checks the schema structure but does not verify that the security requirement is correctly applied when the endpoint dependency is used. The schema shows security: [{"OAuth2PasswordBearer": []}] but does not test enforcement.

**Source evidence**

````text
def test_openapi_schema():
    response = client.get("/openapi.json")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "openapi": "3.1.0",
        "info": {"title": "FastAPI", "version": "0.1.0"},
        "paths": {
            "/items/": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "Successful Response",
                            "content": {"application/json": {"schema": {}}},
                        }
                    },
                    "summary": "Read Items",
                    "operationId": "read_items_items__get",
                    "security": [{"OAuth2PasswordBearer": []}],
                }
            }
        },
        "components": {
            "securitySchemes": {
                "OAuth2PasswordBearer": {
                    "type": "oauth2",
                    "flows": {"password": {"scopes": {}, "tokenUrl": "token"}},
                }
            }
        },
    }
````

**Recommendation:** Add a test that attempts to access the endpoint without any Authorization header when the schema requires OAuth2, and confirm 401 is returned.

**Suggested test:** def test_security_enforcement(client):\n    response = client.get("/items")\n    assert response.status_code == 401\n    assert response.headers["WWW-Authenticate"] == "Bearer"

### CR-009 · LOW · Test 'test_incorrect_token' sends a bare string instead of 'Bearer <token>' format

`tests/test_tutorial/test_security/test_tutorial001.py:22-23` · Agents: bugs · Confidence: 70%

The test sends 'Notexistent testtoken' as the raw Authorization header value. FastAPI's OAuth2PasswordBearer expects the header to be formatted as 'Bearer <token>'. Sending a bare string may result in a different error path (e.g., 403 or parsing error) than the 'Not authenticated' detail the test asserts, making the test fragile across FastAPI versions.

**Source evidence**

````text
    response = client.get("/items", headers={"Authorization": "Notexistent testtoken"})
    assert response.status_code == 401, response.text
````

**Recommendation:** Change the header to 'Bearer Notexistent testtoken' to properly exercise the OAuth2 Bearer token parsing path and match the expected 'Not authenticated' response.

**Suggested test:** Run the test with 'Bearer Notexistent testtoken' and assert 401 with 'Not authenticated' detail and 'Bearer' WWW-Authenticate header.

### CR-010 · INFO · OAuth2PasswordBearer tokenUrl points to non-existent endpoint

`docs_src/security/tutorial001.py:6-6` · Agents: security · Confidence: 100%

The OAuth2PasswordBearer dependency is configured with tokenUrl='token', but no corresponding token generation endpoint is defined in this tutorial file. This is intentional for an introductory example; callers must implement the token endpoint separately.

**Source evidence**

````text
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
````

**Recommendation:** Document that a token endpoint at /token (or the configured URL) must be implemented outside this tutorial, or adjust tokenUrl to match the actual endpoint if provided.

### CR-011 · INFO · Production code lacks token endpoint definition

`docs_src/security/tutorial001.py:6-6` · Agents: tests · Confidence: 95%

OAuth2PasswordBearer is instantiated with tokenUrl="token" but no FastAPI route defining the "token" endpoint exists in this snapshot. This is typical for introductory tutorials that defer token generation to a later lesson.

**Source evidence**

````text
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
````

**Recommendation:** Either add a minimal token endpoint or update the comment/docstring to note that the token endpoint is defined elsewhere.

## Next steps

- Add a '/token' route or document that tokenUrl points to an external auth service; update OpenAPI schema accordingly.
- Implement token validation logic (JWT decode/introspection) in read_items before echoing the token value.
- Add test cases for empty Bearer token, token refresh/revocation, and security enforcement (401 without auth header).
- Fix test_incorrect_token to use 'Bearer Notexistent testtoken' header format to properly exercise OAuth2 parsing.
- If a token endpoint is added, integrate rate limiting and brute-force mitigation.

## Specialist results

- **bugs — completed:** Review of FastAPI OAuth2 introductory tutorial snapshot. No critical or high-severity bugs were found in the minimal code. The tutorial correctly demonstrates OAuth2PasswordBearer usage with tokenUrl. The test suite covers basic auth flow (missing/no token, valid token, incorrect token, OpenAPI schema). One medium finding regarding missing token refresh/revocation patterns is documented, but falls within tutorial scope.
- **security — completed:** Security review of FastAPI OAuth2 tutorial (tutorial001.py and tests). The code presents an introductory OAuth2PasswordBearer pattern with no critical or high-severity vulnerabilities. Findings focus on tutorial scope, missing validation, and test coverage.
- **tests — completed:** Review of FastAPI OAuth2 tutorial snapshot: tutorial code and four existing tests are present. The tests exercise token absence, valid token, incorrect token, and OpenAPI schema output. No test covers token refresh, revocation, scope enforcement, or missing WWW-Authenticate header variations. The production code uses OAuth2PasswordBearer with tokenUrl="token" but no token endpoint is defined in this snapshot. Coverage was not measured.

## Limitations

- Static review only: submitted code was not executed and test coverage was not measured.
- Findings are limited to the submitted source snapshot; dependencies and deployment were not audited.
- The review is based on a single-file tutorial snapshot; broader application code, database integration, and production hardening are out of scope.
- No runtime execution was performed; findings are based on static code analysis of the provided source.
- The tutorial intentionally omits token issuance logic; findings reflect that scope boundary.
- The review is based on a single immutable snapshot of tutorial code; runtime behavior, configuration outside the snapshot, and deployed environment are not visible.
- The tutorial intentionally omits token validation and production hardening for brevity; findings reflect missing pieces rather than exploitable bugs in the supplied code.
- No execution of application code was performed; all analysis is static and based on source inspection.
- Source snapshot is untrusted data; runtime behavior cannot be verified without executing the code.
- Tests were not run; coverage was not measured.
- The tutorial scope is introductory; some missing tests may be intentionally deferred.
- No token endpoint or refresh logic is included in this snapshot.
- Coverage was not measured and tests were not executed; only submitted files were inspected.

## Source manifest

- `docs_src/security/tutorial001.py`: 11 lines; SHA-256 `2982d6ebeb11a3d83de3fb5735306151341b1a34cae8aaede5580ede9f733f5a`
- `tests/test_tutorial/test_security/test_tutorial001.py`: 57 lines; SHA-256 `7c53c55c5cdfd592426a08b030a40cc15e835041d871174d17a0abc8236366ba`
